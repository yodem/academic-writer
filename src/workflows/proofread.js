// proofread — Dynamic-Workflow harness for the unified /academic-writer:proofread pipeline
// (plan of record: internal project plan, Phase 1.2).
//
// Run via: Workflow({ scriptPath: "${CLAUDE_PLUGIN_ROOT}/workflows/proofread.js", args })
//
// This script has NO filesystem access. It reads only `args` and returns change
// lists / a memo / gates; the calling skill (src/skills/proofread/SKILL.md) is
// responsible for every read and write to disk (chunking, spell-check, applying
// changes, building the tracked-changes docx, writing the report).
//
// Three mandatory deltas from the plan's Research digest ("Decisions this
// changes") that OVERRIDE any older prose describing this pipeline:
//
//   (i)   A refute majority NEVER drops a change. It downgrades it to
//         applied=false, skipReason='refuted', refutedBy=[lens keys], and the
//         change still appears in the returned list so the report can show it.
//         Dropping a true positive is the exact hebrew-recall-rejection failure
//         (`להתפשר אם`) this pipeline exists to fix.
//   (ii)  Fresh-vs-seen dedupe keys on NFC-normalized `before` (+ a stable
//         context anchor), NEVER on `line` — the residual pass runs on
//         corrected text where every line below an applied edit has shifted.
//   (iii) Every cap (chunkWords, maxPasses, dryRounds, concurrencyCap,
//         refuteVotes, refuteMajority) is read from args.thresholds — never a
//         literal in this script — and every loop exit is NAMED
//         ('converged' | 'cap-reached'). A missing threshold key blocks the
//         stage that needs it (logged, gated) rather than inventing a default.
//
// Workflow runtime notes (see chain-patterns/references/dynamic-workflow-patterns.md):
// no backticks/${...} interpolation inside agent()/log() prompt strings, no
// TypeScript syntax, `meta` must be a pure literal, no fs/Date.now/Math.random.

export const meta = {
  name: 'academic-writer-proofread',
  description: 'Editorial (venue-fit) memo over the whole article, language (register/collocation) edits refute-verified by three named lenses, and a mechanical (typo/punctuation) convergence loop over chunks — a refute majority only ever downgrades a change, it never drops it.',
  phases: [
    { title: 'Editorial', detail: 'one whole-article agent against the venue profile returns a comment-only memo; never applied' },
    { title: 'Language', detail: 'copyeditor finds per chunk; every change is refute-verified by three named lenses before it may be marked applicable' },
    { title: 'Mechanical', detail: 'proofreader + spell candidates loop per chunk until dry (dryRounds) or the pass cap (maxPasses); each round is a residual pass over corrected text' },
    { title: 'Verify', detail: 'aggregate the refute/downgrade ledger across Language and Mechanical into one accountable summary — nothing dropped is ever silent' },
  ],
};

// -- args guard (a workflow may receive args as a JSON string) --------------
const RAW = typeof args === 'string' && args.trim() ? JSON.parse(args) : args;
const cfg = RAW && typeof RAW === 'object' ? RAW : {};

const language = cfg.language || 'he';
const geminiApproved = cfg.geminiApproved === true;
const venue = cfg.venue || null;
const thresholds = (cfg.thresholds && typeof cfg.thresholds === 'object') ? cfg.thresholds : {};
const chunks = Array.isArray(cfg.chunks) ? cfg.chunks : [];
const spellCandidates = Array.isArray(cfg.spellCandidates) ? cfg.spellCandidates : [];
const requestedStages = Array.isArray(cfg.stages) && cfg.stages.length
  ? cfg.stages
  : ['editorial', 'language', 'mechanical'];
const authorVoice = cfg.authorVoice || null;
const articleText = typeof cfg.articleText === 'string' && cfg.articleText
  ? cfg.articleText
  : chunks.map((c) => c.text).join('\n\n');

// -- thresholds: every cap comes from args.thresholds, never a literal here --
const THRESHOLD_KEYS = ['chunkWords', 'maxPasses', 'dryRounds', 'concurrencyCap', 'refuteVotes', 'refuteMajority'];
const missingThresholdKeys = THRESHOLD_KEYS.filter((k) => thresholds[k] === undefined || thresholds[k] === null);
if (missingThresholdKeys.length) {
  log('WARN: args.thresholds is missing key(s) ' + missingThresholdKeys.join(', ') + ' — the caller must load src/thresholds.json\'s proofread block; stages needing a missing cap will be gated off, never given an invented default.');
}

const chunkWords = thresholds.chunkWords;
const maxPasses = thresholds.maxPasses;
const dryRounds = thresholds.dryRounds;
const concurrencyCap = thresholds.concurrencyCap;
const refuteVotes = thresholds.refuteVotes;
const refuteMajority = thresholds.refuteMajority;

// -- refute fan-out budget: bounds volume, not parallelism (concurrencyCap ---
// -- above bounds parallelism only). Absent/invalid -> today's unbounded ----
// -- behaviour, but logged so the missing cap is visible, never silent. -----
const refuteBudgetPerChunk = thresholds.refuteBudgetPerChunk;
const refuteBudgetIsBounded = typeof refuteBudgetPerChunk === 'number' && refuteBudgetPerChunk > 0;
if (!refuteBudgetIsBounded) {
  log('WARN: args.thresholds.refuteBudgetPerChunk is missing or invalid — the caller must load src/thresholds.json\'s proofread block; refute-verification fan-out is UNBOUNDED for this run (pre-budget behaviour) — every found change is sent for refute-verification with no per-chunk volume cap.');
}

log('proofread workflow: language=' + language + ' geminiApproved=' + geminiApproved + ' chunks=' + chunks.length + ' stages=' + requestedStages.join(','));

// -- shared inline schemas (this script cannot Read changes-schema.json off ---
// -- disk, so the shape it asks agents for is inlined here, kept in sync with
// -- src/skills/proofread/references/changes-schema.json by convention) -----
const CHANGE_ITEM_SCHEMA = {
  type: 'object',
  required: ['stage', 'line', 'type', 'level', 'before', 'rationale', 'meaningRisk'],
  properties: {
    change_id: { type: 'string' },
    stage: { type: 'string', enum: ['editorial', 'language', 'mechanical'] },
    line: { type: 'integer' },
    type: {
      type: 'string',
      enum: [
        'typo', 'punctuation', 'typography', 'agreement', 'word', 'collocation',
        'register', 'syntax', 'tense', 'sentence', 'cut', 'refocus',
        'term-undefined', 'insider-reference', 'genre-fit', 'idea-flag', 'voice-flag',
      ],
    },
    level: { type: 'string', enum: ['letter', 'word', 'sentence', 'paragraph', 'idea'] },
    before: { type: 'string' },
    after: { type: ['string', 'null'] },
    rationale: { type: 'string' },
    meaningRisk: { type: 'string', enum: ['low', 'medium', 'high'] },
    applied: { type: 'boolean' },
    skipReason: { type: ['string', 'null'] },
    refutedBy: { type: 'array', items: { type: 'string' } },
    snippet: { type: 'string' },
    fixWith: { type: 'string' },
  },
};
const CHANGES_SCHEMA = {
  type: 'object',
  required: ['stage', 'changes'],
  properties: {
    stage: { type: 'string', enum: ['editorial', 'language', 'mechanical'] },
    chunk_id: { type: 'string' },
    changes: { type: 'array', items: CHANGE_ITEM_SCHEMA },
    summary: { type: 'string' },
  },
};
const REFUTE_VERDICT_SCHEMA = {
  type: 'object',
  required: ['outcome', 'reason'],
  properties: {
    lens: { type: 'string' },
    outcome: { type: 'string', enum: ['uphold', 'refute'] },
    reason: { type: 'string' },
  },
};

// -- generic helpers ----------------------------------------------------------

// Batches thunks (zero-arg functions returning a promise) into groups of at
// most `cap` and runs each batch with parallel() — the concrete mechanism by
// which args.thresholds.concurrencyCap is enforced, per WRK-14.
async function runCapped(thunks, cap) {
  const safeCap = (typeof cap === 'number' && cap > 0) ? cap : thunks.length;
  const out = [];
  for (let i = 0; i < thunks.length; i += safeCap) {
    const batch = thunks.slice(i, i + safeCap);
    const batchResults = await parallel(batch);
    out.push(...batchResults);
  }
  return out;
}

// Cap-aware find-then-verify shape over chunks, using the Workflow tool's
// pipeline() primitive per the plan's own pseudocode (Phase 1.2): each batch
// of at most `concurrencyCap` chunks runs stage1 then stage2 through
// pipeline(), and the batches themselves run one after another.
async function runPipelineCapped(items, cap, stage1, stage2) {
  const safeCap = (typeof cap === 'number' && cap > 0) ? cap : items.length;
  const out = [];
  for (let i = 0; i < items.length; i += safeCap) {
    const batch = items.slice(i, i + safeCap);
    const batchResults = await pipeline(batch, stage1, stage2);
    out.push(...batchResults);
  }
  return out;
}

function normalizeText(text) {
  return (typeof text === 'string' ? text : '').normalize('NFC').trim();
}

// Dedupe key: NFC-normalized `before` anchored by the chunk it was found in
// and its type — deliberately NOT the line number (mandate ii). `chunk_id`
// plus `before` is a stable anchor across rounds even though every line below
// an applied edit shifts once the residual pass runs on corrected text.
function changeKey(change) {
  return (change.chunk_id || 'whole-article') + '::' + (change.type || '') + '::' + normalizeText(change.before);
}

// Highest-meaningRisk-first ordering for spending a bounded refute budget:
// exhausting the budget should degrade gracefully (drop verification rigor
// on the least-risky changes first), not arbitrarily by list order.
const MEANING_RISK_SPEND_ORDER = ['high', 'medium', 'low'];
function meaningRiskRank(risk) {
  const rank = MEANING_RISK_SPEND_ORDER.indexOf(risk);
  return rank === -1 ? MEANING_RISK_SPEND_ORDER.length : rank;
}

// Splits a set of found changes into { toVerify, exhausted } against a
// remaining budget, spending the budget on the highest meaningRisk changes
// first. Changes beyond the budget are NEVER dropped by this function --
// the caller carries them with skipReason 'refute-budget-exhausted'
// (mandate i, extended to the budget gate).
//
// `budget` is UNBOUNDED only when it is not a number at all (missing/invalid
// threshold -- pre-budget behaviour, every change goes to toVerify). A
// numeric budget of zero or less is a real, spent-out budget, NOT unbounded
// -- that distinction matters for the mechanical stage, which calls this once
// per chunk per residual round and must treat "budget already spent in an
// earlier round" as zero remaining, not as "no cap configured".
function splitByRefuteBudget(changes, budget) {
  if (typeof budget !== 'number') {
    return { toVerify: changes, exhausted: [] };
  }
  const safeBudget = budget > 0 ? budget : 0;
  if (changes.length <= safeBudget) {
    return { toVerify: changes, exhausted: [] };
  }
  const ranked = changes
    .map((change, index) => ({ change, index }))
    .sort((a, b) => {
      const byRisk = meaningRiskRank(a.change.meaningRisk) - meaningRiskRank(b.change.meaningRisk);
      return byRisk !== 0 ? byRisk : a.index - b.index;
    })
    .map((entry) => entry.change);
  return { toVerify: ranked.slice(0, safeBudget), exhausted: ranked.slice(safeBudget) };
}

function spellCandidatesFor(chunk) {
  const start = chunk.startLine;
  const end = chunk.endLine;
  if (typeof start !== 'number' || typeof end !== 'number') return [];
  return spellCandidates.filter((c) => typeof c.line === 'number' && c.line >= start && c.line <= end);
}

// Best-effort IN-MEMORY application of a change to a working chunk copy, so
// the next mechanical round's finder reads a residual/corrected view rather
// than the same text again (the "second lens" of the plan's two-pass model).
// This never touches disk — the skill's apply-changes.py is the authoritative
// application against PROOF_BASE.
function applyChangeInMemory(text, change) {
  if (typeof change.after !== 'string') return text;
  const before = change.before;
  if (typeof before !== 'string' || !before) return text;
  const idx = text.indexOf(before);
  if (idx === -1) return text;
  return text.slice(0, idx) + change.after + text.slice(idx + before.length);
}

function applyRoundInMemory(workingChunks, appliedThisRound) {
  const byChunk = new Map();
  for (const change of appliedThisRound) {
    if (change.meaningRisk !== 'low' || change.skipReason) continue;
    const list = byChunk.get(change.chunk_id) || [];
    list.push(change);
    byChunk.set(change.chunk_id, list);
  }
  return workingChunks.map((c) => {
    const forChunk = byChunk.get(c.id);
    if (!forChunk || !forChunk.length) return c;
    let text = c.text;
    for (const change of forChunk) {
      text = applyChangeInMemory(text, change);
    }
    return { ...c, text };
  });
}

const gates = [];

// -----------------------------------------------------------------------
// Editorial
// -----------------------------------------------------------------------
phase('Editorial');

let memo = null;
if (requestedStages.indexOf('editorial') !== -1) {
  const venueText = venue && typeof venue === 'object' && venue.profile
    ? venue.profile
    : (typeof venue === 'string' ? venue : null);
  const editorialPrompt = [
    'You are the עורך: a whole-article editorial pre-submission review against a venue profile.',
    'ARTICLE_TEXT (full article, with line numbers):',
    articleText,
    'VENUE_PROFILE: ' + (venueText || 'none supplied — evaluate against general academic-publishing norms and say so in your summary.'),
    'LANGUAGE: ' + language,
    'Return exactly one JSON object matching the editorial changes-schema contract: stage="editorial" at the top level and on every change, after=null on every change, meaningRisk="high" on every change (comment-only signal, not a graded risk).',
  ].join('\n');
  memo = await agent(editorialPrompt, {
    agentType: 'academic-writer:editor',
    label: 'editorial',
    phase: 'Editorial',
    model: 'opus',
    schema: CHANGES_SCHEMA,
  });
  gates.push({
    stage: 'editorial',
    ran: true,
    why: 'requested via args.stages',
    model: 'opus',
    rounds: 1,
    outcome: memo && Array.isArray(memo.changes) ? (memo.changes.length + ' finding(s)') : 'memo returned',
  });
} else {
  gates.push({ stage: 'editorial', ran: false, why: 'not requested (args.stages excludes editorial)', model: null, rounds: null, outcome: 'skipped' });
}

// -----------------------------------------------------------------------
// Language
// -----------------------------------------------------------------------
phase('Language');

const LANGUAGE_LENSES = ['meaning-preserved', 'standard-language', 'voice-preserved'];

function lensPrompt(lens, change) {
  const focus = lens === 'meaning-preserved'
    ? 'Does AFTER preserve the exact meaning, claim and argument of BEFORE? Refute if meaning shifts at all, even subtly.'
    : lens === 'standard-language'
      ? 'Is AFTER standard, idiomatic academic ' + language + ' — not itself a new error, and a genuine improvement on BEFORE? Refute if AFTER is non-standard or no better than BEFORE.'
      : 'Does AFTER preserve the author\'s voice (register, rhythm, personal phrasing) rather than flattening it toward generic prose? Refute if voice is lost.';
  return [
    'Adversarial refute-lens: ' + lens + '. You are BLIND to the finder\'s own reasoning — judge ONLY this one lens, independently.',
    'BEFORE: ' + JSON.stringify(change.before),
    'AFTER: ' + JSON.stringify(change.after),
    'PROPOSED RATIONALE (do not defer to it — verify independently): ' + JSON.stringify(change.rationale),
    focus,
    'Return JSON only: {"lens": "' + lens + '", "outcome": "uphold" or "refute", "reason": "..."}.',
  ].join('\n');
}

async function refuteChange(change, lensNames, cap) {
  const thunks = lensNames.map((lens) => () => agent(lensPrompt(lens, change), {
    model: 'opus',
    label: 'refute:' + lens + ':' + (change.chunk_id || 'x'),
    phase: 'Language',
    schema: REFUTE_VERDICT_SCHEMA,
  }));
  const votes = await runCapped(thunks, cap);
  const refuted = votes.filter((v) => v && v.outcome === 'refute');
  return { votes, refutedBy: refuted.map((v) => v.lens || 'unnamed-lens') };
}

let languageChanges = [];
const canRunLanguage = chunks.length > 0 && typeof concurrencyCap === 'number' && typeof refuteMajority === 'number';
if (requestedStages.indexOf('language') !== -1 && canRunLanguage) {
  function languageFindStage(chunk) {
    const prompt = [
      'You are the עורך לשוני for one bounded chunk of an academic article.',
      'CHUNK_ID: ' + chunk.id,
      'CHUNK_TEXT (with 1-based line numbers already offset-corrected to PROOF_BASE):',
      chunk.text,
      'LANGUAGE: ' + language,
      authorVoice ? ('AUTHOR_VOICE:\n' + authorVoice) : 'AUTHOR_VOICE: none supplied.',
      'Return exactly one JSON object matching the language changes-schema contract: stage="language" at the top level AND on every change, chunk_id="' + chunk.id + '".',
    ].join('\n');
    return agent(prompt, {
      agentType: 'academic-writer:copyeditor',
      label: 'language-find:' + chunk.id,
      phase: 'Language',
      model: 'opus',
      schema: CHANGES_SCHEMA,
    }).then((result) => ({ chunk, result }));
  }
  async function languageVerifyStage(found) {
    const list = (found.result && Array.isArray(found.result.changes)) ? found.result.changes : [];
    const stamped = list.map((rawChange) => ({ ...rawChange, stage: 'language', chunk_id: found.chunk.id }));
    const budgeted = splitByRefuteBudget(stamped, refuteBudgetPerChunk);
    const verifiedChanges = [];
    for (const change of budgeted.toVerify) {
      const lensNames = (typeof refuteVotes === 'number' && refuteVotes > 0 && refuteVotes <= LANGUAGE_LENSES.length)
        ? LANGUAGE_LENSES.slice(0, refuteVotes)
        : LANGUAGE_LENSES;
      const verdict = await refuteChange(change, lensNames, concurrencyCap);
      if (verdict.refutedBy.length >= refuteMajority) {
        log('Language change downgraded — refuted by [' + verdict.refutedBy.join(', ') + ']: ' + normalizeText(change.before));
        verifiedChanges.push({ ...change, applied: false, skipReason: 'refuted', refutedBy: verdict.refutedBy });
      } else {
        verifiedChanges.push(change);
      }
    }
    for (const change of budgeted.exhausted) {
      log('Language change carried WITHOUT refute-verification — refuteBudgetPerChunk exhausted for chunk ' + found.chunk.id + ': ' + normalizeText(change.before));
      verifiedChanges.push({ ...change, applied: false, skipReason: 'refute-budget-exhausted' });
    }
    return { ...found, verifiedChanges };
  }
  const languageResults = await runPipelineCapped(chunks, concurrencyCap, languageFindStage, languageVerifyStage);
  for (const r of languageResults) {
    if (r && Array.isArray(r.verifiedChanges)) {
      languageChanges.push(...r.verifiedChanges);
    }
  }
  const downgraded = languageChanges.filter((c) => c.skipReason === 'refuted').length;
  const budgetExhausted = languageChanges.filter((c) => c.skipReason === 'refute-budget-exhausted').length;
  gates.push({
    stage: 'language',
    ran: true,
    why: 'requested via args.stages',
    model: 'opus',
    rounds: 1,
    outcome: languageChanges.length + ' change(s), ' + downgraded + ' downgraded by refute, '
      + budgetExhausted + ' carried unverified (refute-budget-exhausted)'
      + (refuteBudgetIsBounded ? '' : ' [refuteBudgetPerChunk unbounded]'),
  });
} else if (requestedStages.indexOf('language') === -1) {
  gates.push({ stage: 'language', ran: false, why: 'not requested (args.stages excludes language)', model: null, rounds: null, outcome: 'skipped' });
} else {
  const why = chunks.length === 0 ? 'no chunks supplied' : 'missing args.thresholds.concurrencyCap or refuteMajority';
  gates.push({ stage: 'language', ran: false, why: why, model: null, rounds: null, outcome: 'skipped' });
}

// -----------------------------------------------------------------------
// Mechanical
// -----------------------------------------------------------------------
phase('Mechanical');

let mechanicalChanges = [];
let mechanicalOutcome = 'cap-reached';
let mechanicalRounds = 0;
const canRunMechanical = chunks.length > 0
  && typeof maxPasses === 'number'
  && typeof dryRounds === 'number'
  && typeof concurrencyCap === 'number'
  && typeof refuteVotes === 'number'
  && typeof refuteMajority === 'number';

if (requestedStages.indexOf('mechanical') !== -1 && canRunMechanical) {
  const seen = new Map(); // changeKey -> change, across every round (mandate ii: keyed by before + chunk, never line)
  let workingChunks = chunks.map((c) => ({ ...c }));
  let dryStreak = 0;
  // refuteBudgetPerChunk is a CUMULATIVE per-chunk cap across every
  // mechanical round, not a per-round allowance -- the mechanical loop is a
  // residual pass over the SAME chunks, so a per-round-only budget would let
  // a chunk spend the budget again on every round (up to maxPasses times
  // over). This map tracks how much of the budget each chunk_id has already
  // spent on refute-verification so far.
  const mechanicalBudgetSpent = new Map(); // chunk_id -> count already sent for refute-verification

  async function verifyMechanicalChange(change) {
    const thunks = [];
    for (let v = 0; v < refuteVotes; v += 1) {
      const prompt = [
        'Adversarially refute or uphold ONE proposed mechanical (typo/punctuation/typography/agreement) edit. You are BLIND to the finder\'s own reasoning.',
        'BEFORE: ' + JSON.stringify(change.before),
        'AFTER: ' + JSON.stringify(change.after),
        'PROPOSED RATIONALE (verify independently, do not defer to it): ' + JSON.stringify(change.rationale),
        'Judge ONLY whether this is a genuine mechanical fix and not a meaning, register or wording change in disguise. Refute if it changes anything beyond mechanics.',
        'Return JSON only: {"outcome": "uphold" or "refute", "reason": "..."}.',
      ].join('\n');
      const opts = {
        label: 'mechanical-verify:' + (change.chunk_id || 'x') + ':' + v,
        phase: 'Mechanical',
        schema: REFUTE_VERDICT_SCHEMA,
      };
      if (geminiApproved) {
        // Plan §1.2: geminiApproved routes the verify lens through the Gemini
        // raw MCP tool instead of an Opus refute agent — same REFUTE prompt.
        opts.mcpTool = 'mcp__plugin_academic-writer_gemini-api__gemini_raw';
      } else {
        opts.model = 'opus';
      }
      thunks.push(() => agent(prompt, opts));
    }
    const votes = await runCapped(thunks, refuteVotes);
    const refuted = votes.filter((v) => v && v.outcome === 'refute');
    return { refutedCount: refuted.length, refutedBy: refuted.map((v, i) => 'lens-' + i) };
  }

  function mechanicalFindStage(chunk) {
    const prompt = [
      'You are the מגיה for one bounded chunk of an academic article. This is round ' + (mechanicalRounds + 1) + ' — a residual pass; earlier applied changes are already reflected in CHUNK_TEXT.',
      'CHUNK_ID: ' + chunk.id,
      'CHUNK_TEXT (with 1-based line numbers already offset-corrected to PROOF_BASE):',
      chunk.text,
      'LANGUAGE: ' + language,
      'spellCandidates for this chunk (adjudicate one at a time; ignore entirely if empty): ' + JSON.stringify(spellCandidatesFor(chunk)),
      'Return exactly one JSON object matching the mechanical changes-schema contract: stage="mechanical" at the top level AND on every change, chunk_id="' + chunk.id + '".',
    ].join('\n');
    return agent(prompt, {
      agentType: 'academic-writer:proofreader',
      label: 'mechanical-find:' + chunk.id + ':round' + (mechanicalRounds + 1),
      phase: 'Mechanical',
      model: 'sonnet',
      schema: CHANGES_SCHEMA,
    }).then((result) => ({ chunk, result }));
  }

  async function mechanicalVerifyStage(found) {
    const list = (found.result && Array.isArray(found.result.changes)) ? found.result.changes : [];
    const freshFound = [];
    for (const rawChange of list) {
      const change = { ...rawChange, stage: 'mechanical', chunk_id: found.chunk.id };
      const key = changeKey(change);
      if (seen.has(key)) continue; // already discovered/verified in an earlier round
      seen.set(key, true);
      freshFound.push(change);
    }
    const chunkId = found.chunk.id;
    const alreadySpent = mechanicalBudgetSpent.get(chunkId) || 0;
    const remainingBudget = refuteBudgetIsBounded
      ? (refuteBudgetPerChunk > alreadySpent ? refuteBudgetPerChunk - alreadySpent : 0)
      : refuteBudgetPerChunk; // unbounded stays unbounded (not a number)
    const budgeted = splitByRefuteBudget(freshFound, remainingBudget);
    mechanicalBudgetSpent.set(chunkId, alreadySpent + budgeted.toVerify.length);
    const freshHere = [];
    for (const change of budgeted.toVerify) {
      const verdict = await verifyMechanicalChange(change);
      if (verdict.refutedCount >= refuteMajority) {
        log('Mechanical change downgraded — refuted by ' + verdict.refutedBy.join(', ') + ': ' + normalizeText(change.before));
        freshHere.push({ ...change, applied: false, skipReason: 'refuted', refutedBy: verdict.refutedBy });
      } else {
        freshHere.push(change);
      }
    }
    for (const change of budgeted.exhausted) {
      log('Mechanical change carried WITHOUT refute-verification — refuteBudgetPerChunk exhausted for chunk ' + found.chunk.id + ': ' + normalizeText(change.before));
      freshHere.push({ ...change, applied: false, skipReason: 'refute-budget-exhausted' });
    }
    return { ...found, freshChanges: freshHere };
  }

  while (mechanicalRounds < maxPasses) {
    mechanicalRounds += 1;
    const roundResults = await runPipelineCapped(workingChunks, concurrencyCap, mechanicalFindStage, mechanicalVerifyStage);
    let freshCount = 0;
    const appliedThisRound = [];
    for (const r of roundResults) {
      const freshChanges = (r && Array.isArray(r.freshChanges)) ? r.freshChanges : [];
      freshCount += freshChanges.length;
      mechanicalChanges.push(...freshChanges);
      appliedThisRound.push(...freshChanges);
    }
    log('Mechanical round ' + mechanicalRounds + ': ' + freshCount + ' fresh change(s) (dry streak was ' + dryStreak + ')');
    if (freshCount === 0) {
      dryStreak += 1;
    } else {
      dryStreak = 0;
      workingChunks = applyRoundInMemory(workingChunks, appliedThisRound);
    }
    if (dryStreak >= dryRounds) {
      mechanicalOutcome = 'converged';
      break;
    }
  }
  if (mechanicalRounds >= maxPasses && mechanicalOutcome !== 'converged') {
    mechanicalOutcome = 'cap-reached';
    log('Mechanical loop hit the pass cap (maxPasses=' + maxPasses + ') before going dry for ' + dryRounds + ' consecutive round(s) — outcome=cap-reached, not silently truncated.');
  }
  const downgraded = mechanicalChanges.filter((c) => c.skipReason === 'refuted').length;
  const budgetExhausted = mechanicalChanges.filter((c) => c.skipReason === 'refute-budget-exhausted').length;
  gates.push({
    stage: 'mechanical',
    ran: true,
    why: 'requested via args.stages',
    model: 'sonnet',
    rounds: mechanicalRounds,
    outcome: mechanicalOutcome + ' — ' + mechanicalChanges.length + ' change(s), ' + downgraded + ' downgraded by refute, '
      + budgetExhausted + ' carried unverified (refute-budget-exhausted)'
      + (refuteBudgetIsBounded ? '' : ' [refuteBudgetPerChunk unbounded]'),
  });
} else if (requestedStages.indexOf('mechanical') === -1) {
  mechanicalOutcome = 'skipped';
  gates.push({ stage: 'mechanical', ran: false, why: 'not requested (args.stages excludes mechanical)', model: null, rounds: null, outcome: 'skipped' });
} else {
  mechanicalOutcome = 'skipped';
  const why = chunks.length === 0
    ? 'no chunks supplied'
    : 'missing one or more args.thresholds keys: maxPasses, dryRounds, concurrencyCap, refuteVotes, refuteMajority';
  gates.push({ stage: 'mechanical', ran: false, why: why, model: null, rounds: null, outcome: 'skipped' });
}

// -----------------------------------------------------------------------
// Verify — aggregate the ledger; nothing dropped is ever silent
// -----------------------------------------------------------------------
phase('Verify');

const languageDowngraded = languageChanges.filter((c) => c.skipReason === 'refuted');
const mechanicalDowngraded = mechanicalChanges.filter((c) => c.skipReason === 'refuted');
const languageBudgetExhausted = languageChanges.filter((c) => c.skipReason === 'refute-budget-exhausted');
const mechanicalBudgetExhausted = mechanicalChanges.filter((c) => c.skipReason === 'refute-budget-exhausted');
log('Verify: ' + languageDowngraded.length + ' language change(s) and ' + mechanicalDowngraded.length + ' mechanical change(s) downgraded by refute — none dropped, all still present in the returned lists.');
log('Verify: ' + languageBudgetExhausted.length + ' language change(s) and ' + mechanicalBudgetExhausted.length + ' mechanical change(s) carried unverified because refuteBudgetPerChunk was exhausted — none dropped, all still present in the returned lists.');
gates.push({
  stage: 'verify',
  ran: true,
  why: 'aggregate refute/downgrade ledger across Language and Mechanical (VER-10 / SPC-14)',
  model: null,
  rounds: null,
  outcome: languageDowngraded.length + ' language downgrade(s), ' + mechanicalDowngraded.length + ' mechanical downgrade(s), '
    + languageBudgetExhausted.length + ' language + ' + mechanicalBudgetExhausted.length + ' mechanical budget-exhausted',
});

return {
  memo: memo,
  languageChanges: languageChanges,
  mechanicalChanges: mechanicalChanges,
  outcome: mechanicalOutcome,
  rounds: mechanicalRounds,
  gates: gates,
};
