#!/usr/bin/env python3
"""
Academic Writer — Computational Style Metrics Extraction

Extracts 30+ numerical writing metrics from Hebrew academic articles.
No NLP libraries required — uses regex-based Hebrew tokenization.

Usage:
    python3 extract-style-metrics.py --input past-articles/article.md --json
    python3 extract-style-metrics.py --input past-articles/ --aggregate --json
    python3 extract-style-metrics.py --input past-articles/ --aggregate --baseline hebrew-academic-baseline.json --contrastive

Input: Markdown (.md), plain text (.txt), or directory of files
Output: JSON with numerical metrics for style fingerprinting
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median, stdev


# ─── Hebrew Language Constants ───────────────────────────────────────────────

# Hebrew stopwords (common function words, not content-bearing)
HEBREW_STOPWORDS = {
    'של', 'את', 'על', 'עם', 'אל', 'מן', 'כי', 'לא', 'גם', 'או', 'כל',
    'היא', 'הוא', 'הם', 'הן', 'זה', 'זו', 'זאת', 'אלה', 'אלו',
    'אם', 'יש', 'אין', 'עוד', 'רק', 'כבר', 'מה', 'מי', 'איך', 'למה',
    'הזה', 'הזאת', 'כך', 'לכך', 'בכך', 'שם', 'פה', 'כאן',
    'ה', 'ו', 'ב', 'כ', 'ל', 'מ', 'ש',
    'היה', 'היו', 'היתה', 'יהיה', 'תהיה', 'יהיו',
    'אשר', 'אך', 'כן', 'כמו', 'עד', 'בין', 'לפי', 'אחר', 'בעוד',
    'כדי', 'משום', 'מפני', 'ביותר', 'כלומר', 'אלא', 'אפילו', 'דווקא',
    'לפני', 'אחרי', 'תחת', 'מאוד', 'מאד', 'ממש', 'כלל', 'לגמרי',
    'ממנו', 'ממנה', 'אליו', 'אליה', 'עליו', 'עליה', 'שלו', 'שלה',
}

# First-person markers in Hebrew
FIRST_PERSON_MARKERS = {
    'אני', 'אנו', 'אנחנו', 'לדעתי', 'דעתי', 'לטענתי', 'טענתי',
    'אסביר', 'אבחן', 'אטען', 'אראה', 'אוכיח', 'אסקור', 'ארצה',
    'אגיד', 'אציין', 'אנתח', 'אבקש', 'אדגיש', 'אומר', 'סבור',
    'לי', 'שלי', 'עבורי', 'מבחינתי',
    'אני סבור', 'אני טוען', 'אני מאמין',
    'נבחן', 'נראה', 'נטען', 'נוכיח', 'נסביר',  # first person plural
}

# Passive voice markers (Hebrew nif'al and pu'al patterns)
PASSIVE_MARKERS = [
    r'\bנ\w+[הת]\b',     # nif'al pattern
    r'\bנעשה\b', r'\bנמצא\b', r'\bנראה\b', r'\bנאמר\b', r'\bנחשב\b',
    r'\bנתפס\b', r'\bנעשית\b', r'\bנוצר\b', r'\bנבנה\b', r'\bנכתב\b',
    r'\bהוחלט\b', r'\bהוגדר\b', r'\bהובא\b', r'\bהוצג\b', r'\bהומצא\b',
    r'\bהושמד\b', r'\bהושג\b', r'\bהוכח\b', r'\bהואשם\b', r'\bהורכב\b',
]

# Transition/linking word categories
TRANSITION_CATEGORIES = {
    'addition': [
        'בנוסף', 'מעבר לכך', 'גם', 'וגם', 'כמו כן', 'אף', 'יתרה מכך',
        'זאת ועוד', 'נוסף על כך', 'לצד זאת',
    ],
    'contrast': [
        'אולם', 'מנגד', 'בניגוד ל', 'אך', 'עם זאת', 'אלא ש', 'לעומת זאת',
        'מצד אחד', 'מצד שני', 'ואילו', 'למרות', 'על אף',
    ],
    'causation': [
        'לפיכך', 'על כן', 'כתוצאה מכך', 'משום ש', 'בשל', 'מפני ש',
        'לכן', 'כיוון ש', 'מאחר ש', 'בגלל', 'עקב',
    ],
    'exemplification': [
        'למשל', 'לדוגמה', 'כפי שמשתקף', 'כגון', 'דוגמה לכך',
        'דוגמה מובהקת', 'כפי ש', 'כשם ש',
    ],
    'conclusion': [
        'לסיכום', 'בכך', 'למעשה', 'אם כן', 'נמצא ש', 'מכאן ש',
        'לאור האמור', 'בסיכומו של דבר', 'מכל האמור', 'סוף דבר',
    ],
}


# ─── Text Processing ─────────────────────────────────────────────────────────

def extract_text_from_file(filepath: str) -> str:
    """Extract text from a file (MD, TXT, DOCX, PDF)."""
    path = Path(filepath)
    ext = path.suffix.lower()

    if ext in ('.md', '.txt', ''):
        with open(filepath, 'r', encoding='utf-8') as f:
            text = f.read()
        # Strip markdown headers and formatting
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        return text

    elif ext == '.docx':
        try:
            from docx import Document
            d = Document(filepath)
            # Use double newline between paragraphs so split_paragraphs() works
            return '\n\n'.join(p.text for p in d.paragraphs if p.text.strip())
        except ImportError:
            print("Warning: python-docx not installed, skipping DOCX file", file=sys.stderr)
            return ""

    elif ext == '.pdf':
        try:
            import pdfplumber
            with pdfplumber.open(filepath) as pdf:
                return '\n'.join(page.extract_text() or '' for page in pdf.pages)
        except ImportError:
            print("Warning: pdfplumber not installed, skipping PDF file", file=sys.stderr)
            return ""

    else:
        print(f"Warning: unsupported file type: {ext}", file=sys.stderr)
        return ""


def split_sentences(text: str) -> list[str]:
    """Split Hebrew text into sentences."""
    # Hebrew sentence endings: period, question mark, exclamation mark
    # Careful not to split on abbreviations like עמ' or ר'
    sentences = re.split(
        r'(?<=[.!?])\s+(?=[א-תA-Z\u05D0-\u05EA])',
        text
    )
    # Filter out very short fragments (likely not real sentences)
    return [s.strip() for s in sentences if len(s.strip().split()) >= 3]


def split_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs."""
    paragraphs = re.split(r'\n\s*\n', text)
    return [p.strip() for p in paragraphs if len(p.strip().split()) >= 5]


def tokenize_hebrew(text: str) -> list[str]:
    """Tokenize Hebrew text into words."""
    # Remove punctuation and numbers, keep Hebrew chars and spaces
    words = re.findall(r'[\u05D0-\u05EA]+(?:[\u05D0-\u05EA\-\']+[\u05D0-\u05EA]+)*', text)
    return [w for w in words if len(w) >= 2]


def count_citations(text: str) -> int:
    """Count citation parentheses in text."""
    # Hebrew inline-parenthetical: (Author, Title, עמ' Page)
    inline_cites = len(re.findall(r'\([^)]*(?:עמ\'|שם|עמוד|ibid|pp?\.|p\.)[^)]*\)', text))
    # Also count other parenthetical citations
    paren_cites = len(re.findall(r'\([^)]{5,80}\)', text))
    # Footnotes
    footnotes = len(re.findall(r'\[\^?\d+\]', text))
    return max(inline_cites, paren_cites // 2) + footnotes


def count_quotes(text: str) -> list[int]:
    """Count quoted passages and return their word lengths."""
    # Hebrew gereshayim or regular quotes
    quotes = re.findall(r'[״""]([^״""]{5,})[״""]', text)
    return [len(q.split()) for q in quotes]


# ─── Metrics Extraction ──────────────────────────────────────────────────────

def extract_metrics(text: str) -> dict:
    """
    Extract 30+ numerical writing metrics from text.

    Returns a structured dict with all metrics.
    """
    sentences = split_sentences(text)
    paragraphs = split_paragraphs(text)
    words = tokenize_hebrew(text)
    all_text_lower = text

    if not sentences or not words:
        return {"error": "Insufficient text for analysis"}

    # ── Sentence Level ────────────────────────────────────────────────────

    sentence_word_counts = [len(tokenize_hebrew(s)) for s in sentences]
    sentence_word_counts = [c for c in sentence_word_counts if c > 0]

    sent_mean = mean(sentence_word_counts) if sentence_word_counts else 0
    sent_median = median(sentence_word_counts) if sentence_word_counts else 0
    sent_stdev = stdev(sentence_word_counts) if len(sentence_word_counts) > 1 else 0
    sent_min = min(sentence_word_counts) if sentence_word_counts else 0
    sent_max = max(sentence_word_counts) if sentence_word_counts else 0

    # Sentence length distribution buckets
    buckets = {'under_10': 0, '10_20': 0, '20_30': 0, '30_40': 0, 'over_40': 0}
    for c in sentence_word_counts:
        if c < 10: buckets['under_10'] += 1
        elif c < 20: buckets['10_20'] += 1
        elif c < 30: buckets['20_30'] += 1
        elif c < 40: buckets['30_40'] += 1
        else: buckets['over_40'] += 1

    total_sents = len(sentence_word_counts)
    sent_distribution = {
        k: round(v / total_sents, 3) if total_sents > 0 else 0
        for k, v in buckets.items()
    }

    # Sentence openers (first 3 words)
    openers = []
    for s in sentences:
        words_in_s = tokenize_hebrew(s)
        if len(words_in_s) >= 3:
            opener = ' '.join(words_in_s[:3])
            openers.append(opener)
        elif len(words_in_s) >= 1:
            openers.append(words_in_s[0])

    opener_counter = Counter(openers)
    top_openers = [{'opener': opener, 'count': count, 'frequency': round(count / total_sents, 3)}
                   for opener, count in opener_counter.most_common(20)]

    # First-word counter (for sentence starters)
    first_words = []
    for s in sentences:
        ws = tokenize_hebrew(s)
        if ws:
            first_words.append(ws[0])
    first_word_counter = Counter(first_words)
    top_first_words = [{'word': w, 'count': c, 'frequency': round(c / total_sents, 3)}
                       for w, c in first_word_counter.most_common(15)]

    # Passive voice frequency
    passive_count = 0
    for s in sentences:
        for pattern in PASSIVE_MARKERS:
            if re.search(pattern, s):
                passive_count += 1
                break  # Count each sentence once
    passive_frequency = round(passive_count / total_sents, 3) if total_sents > 0 else 0

    # First-person usage
    first_person_count = 0
    for s in sentences:
        s_words = set(tokenize_hebrew(s))
        if s_words & FIRST_PERSON_MARKERS:
            first_person_count += 1
        elif any(marker in s for marker in ['אני סבור', 'אני טוען', 'אני מאמין', 'לדעתי']):
            first_person_count += 1
    first_person_frequency = round(first_person_count / total_sents, 3) if total_sents > 0 else 0

    # ── Vocabulary ────────────────────────────────────────────────────────

    total_tokens = len(words)
    unique_tokens = len(set(words))
    type_token_ratio = round(unique_tokens / total_tokens, 4) if total_tokens > 0 else 0

    # Average word length (in characters)
    avg_word_length = round(mean(len(w) for w in words), 2) if words else 0

    # Content words (non-stopwords) — frequency
    content_words = [w for w in words if w not in HEBREW_STOPWORDS]
    content_counter = Counter(content_words)
    top_content_words = [{'word': w, 'count': c}
                         for w, c in content_counter.most_common(30)]

    # ── Paragraph Structure ───────────────────────────────────────────────

    para_word_counts = [len(tokenize_hebrew(p)) for p in paragraphs]
    para_word_counts = [c for c in para_word_counts if c > 0]

    para_mean = mean(para_word_counts) if para_word_counts else 0
    para_median = median(para_word_counts) if para_word_counts else 0
    para_stdev = stdev(para_word_counts) if len(para_word_counts) > 1 else 0

    # Paragraph length distribution
    para_buckets = {'under_50': 0, '50_100': 0, '100_200': 0, '200_300': 0, 'over_300': 0}
    for c in para_word_counts:
        if c < 50: para_buckets['under_50'] += 1
        elif c < 100: para_buckets['50_100'] += 1
        elif c < 200: para_buckets['100_200'] += 1
        elif c < 300: para_buckets['200_300'] += 1
        else: para_buckets['over_300'] += 1

    total_paras = len(para_word_counts)
    para_distribution = {
        k: round(v / total_paras, 3) if total_paras > 0 else 0
        for k, v in para_buckets.items()
    }

    # Sentences per paragraph
    sents_per_para = []
    for p in paragraphs:
        p_sents = split_sentences(p)
        sents_per_para.append(len(p_sents))
    sents_per_para_mean = round(mean(sents_per_para), 1) if sents_per_para else 0

    # ── Transitions & Linking Words ───────────────────────────────────────

    transition_counts = defaultdict(list)
    transition_per_para = []

    for p in paragraphs:
        para_transitions = 0
        for category, phrases in TRANSITION_CATEGORIES.items():
            for phrase in phrases:
                occurrences = len(re.findall(re.escape(phrase), p))
                if occurrences > 0:
                    transition_counts[category].append({
                        'phrase': phrase,
                        'count': occurrences
                    })
                    para_transitions += occurrences
        transition_per_para.append(para_transitions)

    # Aggregate transition data
    transition_summary = {}
    for category, items in transition_counts.items():
        phrase_counter = Counter()
        for item in items:
            phrase_counter[item['phrase']] += item['count']
        transition_summary[category] = [
            {'phrase': p, 'count': c}
            for p, c in phrase_counter.most_common(10)
        ]

    transition_freq_mean = round(mean(transition_per_para), 2) if transition_per_para else 0

    # ── Citations ─────────────────────────────────────────────────────────

    citations_per_para = [count_citations(p) for p in paragraphs]
    citation_density_mean = round(mean(citations_per_para), 2) if citations_per_para else 0
    citation_density_stdev = round(stdev(citations_per_para), 2) if len(citations_per_para) > 1 else 0

    # Quote lengths
    all_quote_lengths = count_quotes(text)
    quote_stats = {
        'total_quotes': len(all_quote_lengths),
        'mean_length_words': round(mean(all_quote_lengths), 1) if all_quote_lengths else 0,
        'short_phrase_pct': round(sum(1 for q in all_quote_lengths if q <= 5) / max(len(all_quote_lengths), 1), 3),
        'medium_pct': round(sum(1 for q in all_quote_lengths if 5 < q <= 20) / max(len(all_quote_lengths), 1), 3),
        'long_pct': round(sum(1 for q in all_quote_lengths if q > 20) / max(len(all_quote_lengths), 1), 3),
    }

    # ── AI Tell Indicators ────────────────────────────────────────────────

    em_dash_count = len(re.findall(r'[—\u2014]', text))
    straight_quote_count = text.count('"')

    # ── Build Result ──────────────────────────────────────────────────────

    return {
        'summary': {
            'totalWords': total_tokens,
            'totalSentences': total_sents,
            'totalParagraphs': total_paras,
            'totalUniqueWords': unique_tokens,
        },
        'sentenceLevel': {
            'length': {
                'mean': round(sent_mean, 1),
                'median': round(sent_median, 1),
                'stdev': round(sent_stdev, 1),
                'min': sent_min,
                'max': sent_max,
            },
            'distribution': sent_distribution,
            'topOpeners': top_openers[:15],
            'topFirstWords': top_first_words[:10],
            'passiveVoiceFrequency': passive_frequency,
            'firstPersonFrequency': first_person_frequency,
        },
        'vocabulary': {
            'typeTokenRatio': type_token_ratio,
            'avgWordLength': avg_word_length,
            'topContentWords': top_content_words[:20],
        },
        'paragraphStructure': {
            'length': {
                'mean': round(para_mean, 1),
                'median': round(para_median, 1),
                'stdev': round(para_stdev, 1),
            },
            'distribution': para_distribution,
            'sentencesPerParagraph': sents_per_para_mean,
        },
        'transitions': {
            'byCategory': transition_summary,
            'frequencyPerParagraph': transition_freq_mean,
            'perParagraphCounts': transition_per_para,
        },
        'citations': {
            'densityPerParagraph': {
                'mean': citation_density_mean,
                'stdev': citation_density_stdev,
            },
            'quoteStats': quote_stats,
        },
        'aiTellIndicators': {
            'emDashCount': em_dash_count,
            'straightQuoteCount': straight_quote_count,
        },
    }


def aggregate_metrics(metrics_list: list[dict]) -> dict:
    """
    Aggregate metrics from multiple articles into a single fingerprint.

    Averages numerical values and unions categorical data.
    """
    if not metrics_list:
        return {}

    n = len(metrics_list)

    def safe_mean(values):
        valid = [v for v in values if v is not None and v != 0]
        return round(mean(valid), 2) if valid else 0

    def safe_stdev(values):
        valid = [v for v in values if v is not None and v != 0]
        return round(stdev(valid), 2) if len(valid) > 1 else 0

    # Aggregate sentence metrics
    sent_means = [m['sentenceLevel']['length']['mean'] for m in metrics_list]
    sent_stdevs = [m['sentenceLevel']['length']['stdev'] for m in metrics_list]
    passive_freqs = [m['sentenceLevel']['passiveVoiceFrequency'] for m in metrics_list]
    first_person_freqs = [m['sentenceLevel']['firstPersonFrequency'] for m in metrics_list]

    # Aggregate vocabulary
    ttrs = [m['vocabulary']['typeTokenRatio'] for m in metrics_list]
    avg_word_lens = [m['vocabulary']['avgWordLength'] for m in metrics_list]

    # Aggregate paragraph structure
    para_means = [m['paragraphStructure']['length']['mean'] for m in metrics_list]
    sents_per_para = [m['paragraphStructure']['sentencesPerParagraph'] for m in metrics_list]

    # Aggregate transitions
    trans_freqs = [m['transitions']['frequencyPerParagraph'] for m in metrics_list]

    # Aggregate citations
    cite_means = [m['citations']['densityPerParagraph']['mean'] for m in metrics_list]

    # Aggregate sentence distributions (average the buckets)
    dist_keys = ['under_10', '10_20', '20_30', '30_40', 'over_40']
    avg_sent_dist = {}
    for key in dist_keys:
        values = [m['sentenceLevel']['distribution'].get(key, 0) for m in metrics_list]
        avg_sent_dist[key] = round(mean(values), 3) if values else 0

    # Union top content words across articles
    word_counter = Counter()
    for m in metrics_list:
        for item in m['vocabulary']['topContentWords']:
            word_counter[item['word']] += item['count']
    top_content = [{'word': w, 'count': c} for w, c in word_counter.most_common(30)]

    # Union transition phrases across articles
    trans_union = defaultdict(Counter)
    for m in metrics_list:
        for category, items in m['transitions']['byCategory'].items():
            for item in items:
                trans_union[category][item['phrase']] += item['count']
    trans_summary = {
        cat: [{'phrase': p, 'count': c} for p, c in counter.most_common(10)]
        for cat, counter in trans_union.items()
    }

    # Union sentence openers
    opener_counter = Counter()
    for m in metrics_list:
        for item in m['sentenceLevel']['topOpeners']:
            opener_counter[item['opener']] += item['count']
    top_openers = [{'opener': o, 'count': c} for o, c in opener_counter.most_common(20)]

    # Union first words
    first_word_counter = Counter()
    for m in metrics_list:
        for item in m['sentenceLevel']['topFirstWords']:
            first_word_counter[item['word']] += item['count']
    top_first_words = [{'word': w, 'count': c} for w, c in first_word_counter.most_common(15)]

    total_words = sum(m['summary']['totalWords'] for m in metrics_list)
    total_sents = sum(m['summary']['totalSentences'] for m in metrics_list)
    total_paras = sum(m['summary']['totalParagraphs'] for m in metrics_list)

    return {
        'articlesAnalyzed': n,
        'summary': {
            'totalWords': total_words,
            'totalSentences': total_sents,
            'totalParagraphs': total_paras,
        },
        'sentenceLevel': {
            'length': {
                'mean': safe_mean(sent_means),
                'stdev': safe_mean(sent_stdevs),
                'crossArticleVariation': safe_stdev(sent_means),
            },
            'distribution': avg_sent_dist,
            'topOpeners': top_openers[:15],
            'topFirstWords': top_first_words[:10],
            'passiveVoiceFrequency': {
                'mean': safe_mean(passive_freqs),
                'stdev': safe_stdev(passive_freqs),
            },
            'firstPersonFrequency': {
                'mean': safe_mean(first_person_freqs),
                'stdev': safe_stdev(first_person_freqs),
            },
        },
        'vocabulary': {
            'typeTokenRatio': {
                'mean': safe_mean(ttrs),
                'stdev': safe_stdev(ttrs),
            },
            'avgWordLength': {
                'mean': safe_mean(avg_word_lens),
                'stdev': safe_stdev(avg_word_lens),
            },
            'topContentWords': top_content[:20],
        },
        'paragraphStructure': {
            'length': {
                'mean': safe_mean(para_means),
                'stdev': safe_stdev(para_means),
            },
            'sentencesPerParagraph': {
                'mean': safe_mean(sents_per_para),
            },
        },
        'transitions': {
            'byCategory': trans_summary,
            'frequencyPerParagraph': {
                'mean': safe_mean(trans_freqs),
                'stdev': safe_stdev(trans_freqs),
            },
        },
        'citations': {
            'densityPerParagraph': {
                'mean': safe_mean(cite_means),
                'stdev': safe_stdev(cite_means),
            },
        },
    }


def compute_contrastive(aggregated: dict, baseline: dict) -> dict:
    """
    Compute contrastive scores: how the researcher deviates from baseline.

    For each metric, compute:
        deviation = (researcher_value - baseline_value) / baseline_stdev

    Classification:
        > +1.5  → "distinctively_high"
        < -1.5  → "distinctively_low"
        otherwise → "typical"
    """
    def classify(deviation):
        if deviation > 1.5:
            return 'distinctively_high'
        elif deviation < -1.5:
            return 'distinctively_low'
        else:
            return 'typical'

    def safe_deviation(researcher_val, baseline_val, baseline_std):
        if baseline_std == 0 or baseline_std is None:
            return 0.0
        return round((researcher_val - baseline_val) / baseline_std, 2)

    contrastive = {}

    # Compare each available metric
    comparisons = [
        ('sentenceLength', 'sentenceLevel.length.mean', 'sentenceLevel.length.mean'),
        ('passiveVoice', 'sentenceLevel.passiveVoiceFrequency.mean', 'sentenceLevel.passiveVoiceFrequency'),
        ('firstPerson', 'sentenceLevel.firstPersonFrequency.mean', 'sentenceLevel.firstPersonFrequency'),
        ('typeTokenRatio', 'vocabulary.typeTokenRatio.mean', 'vocabulary.typeTokenRatio'),
        ('avgWordLength', 'vocabulary.avgWordLength.mean', 'vocabulary.avgWordLength'),
        ('paragraphLength', 'paragraphStructure.length.mean', 'paragraphStructure.length.mean'),
        ('transitionFrequency', 'transitions.frequencyPerParagraph.mean', 'transitions.frequencyPerParagraph'),
        ('citationDensity', 'citations.densityPerParagraph.mean', 'citations.densityPerParagraph'),
    ]

    def get_nested(d, path):
        keys = path.split('.')
        for k in keys:
            if isinstance(d, dict):
                d = d.get(k, None)
            else:
                return None
        return d

    for name, researcher_path, baseline_path in comparisons:
        r_val = get_nested(aggregated, researcher_path)
        b_val = get_nested(baseline, baseline_path + '.mean') if baseline else None
        b_std = get_nested(baseline, baseline_path + '.stdev') if baseline else None

        if r_val is not None and b_val is not None and b_std is not None and b_std > 0:
            dev = safe_deviation(r_val, b_val, b_std)
            contrastive[name] = {
                'researcherValue': r_val,
                'baselineValue': b_val,
                'baselineStdev': b_std,
                'deviation': dev,
                'classification': classify(dev),
            }

    return contrastive


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Extract style metrics from Hebrew academic articles',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--input', required=True,
                       help='File path or directory of articles')
    parser.add_argument('--json', action='store_true',
                       help='Output as JSON')
    parser.add_argument('--aggregate', action='store_true',
                       help='Aggregate metrics from multiple files')
    parser.add_argument('--baseline', default=None,
                       help='Path to baseline JSON for contrastive analysis')
    parser.add_argument('--contrastive', action='store_true',
                       help='Include contrastive scores against baseline')
    parser.add_argument('--output', default=None,
                       help='Output file path (default: stdout)')
    args = parser.parse_args()

    input_path = Path(args.input)

    # Collect files
    if input_path.is_dir():
        files = sorted([
            str(f) for f in input_path.iterdir()
            if f.suffix.lower() in ('.md', '.txt', '.docx', '.pdf')
        ])
    elif input_path.is_file():
        files = [str(input_path)]
    else:
        print(f"Error: {input_path} not found", file=sys.stderr)
        sys.exit(1)

    if not files:
        print(f"Error: No supported files found in {input_path}", file=sys.stderr)
        sys.exit(1)

    # Extract metrics from each file
    all_metrics = []
    for filepath in files:
        text = extract_text_from_file(filepath)
        if not text or len(text.split()) < 50:
            print(f"Skipping {filepath} (too short)", file=sys.stderr)
            continue
        metrics = extract_metrics(text)
        if 'error' not in metrics:
            metrics['sourceFile'] = os.path.basename(filepath)
            all_metrics.append(metrics)
            print(f"Extracted: {filepath} ({metrics['summary']['totalWords']} words, "
                  f"{metrics['summary']['totalSentences']} sentences)", file=sys.stderr)

    if not all_metrics:
        print("Error: No valid articles to analyze", file=sys.stderr)
        sys.exit(1)

    # Build result
    if args.aggregate or len(all_metrics) > 1:
        result = aggregate_metrics(all_metrics)
        result['perArticle'] = [
            {
                'file': m['sourceFile'],
                'words': m['summary']['totalWords'],
                'sentences': m['summary']['totalSentences'],
                'sentenceLengthMean': m['sentenceLevel']['length']['mean'],
                'passiveFreq': m['sentenceLevel']['passiveVoiceFrequency'],
                'firstPersonFreq': m['sentenceLevel']['firstPersonFrequency'],
            }
            for m in all_metrics
        ]
    else:
        result = all_metrics[0]

    # Contrastive analysis
    if args.contrastive and args.baseline:
        baseline_path = Path(args.baseline)
        if baseline_path.exists():
            with open(baseline_path, 'r', encoding='utf-8') as f:
                baseline = json.load(f)
            result['contrastive'] = compute_contrastive(result, baseline)
        else:
            print(f"Warning: baseline file not found: {args.baseline}", file=sys.stderr)

    # Output
    if args.json:
        output = json.dumps(result, ensure_ascii=False, indent=2)
    else:
        # Human-readable summary
        lines = []
        if 'articlesAnalyzed' in result:
            lines.append(f"Articles analyzed: {result['articlesAnalyzed']}")
        s = result.get('summary', {})
        lines.append(f"Total words: {s.get('totalWords', 'N/A')}")
        lines.append(f"Total sentences: {s.get('totalSentences', 'N/A')}")
        lines.append(f"Total paragraphs: {s.get('totalParagraphs', 'N/A')}")

        sl = result.get('sentenceLevel', {}).get('length', {})
        lines.append(f"\nSentence length: mean={sl.get('mean', 'N/A')}, stdev={sl.get('stdev', 'N/A')}")

        pv = result.get('sentenceLevel', {}).get('passiveVoiceFrequency', {})
        if isinstance(pv, dict):
            lines.append(f"Passive voice: {pv.get('mean', 'N/A')}")
        else:
            lines.append(f"Passive voice: {pv}")

        fp = result.get('sentenceLevel', {}).get('firstPersonFrequency', {})
        if isinstance(fp, dict):
            lines.append(f"First person: {fp.get('mean', 'N/A')}")
        else:
            lines.append(f"First person: {fp}")

        if 'contrastive' in result:
            lines.append("\nContrastive Analysis:")
            for dim, data in result['contrastive'].items():
                cls = data['classification']
                dev = data['deviation']
                rv = data['researcherValue']
                bv = data['baselineValue']
                marker = '🔵' if cls == 'typical' else '🟢' if 'high' in cls else '🔴'
                lines.append(f"  {marker} {dim}: {rv} (baseline: {bv}, deviation: {dev:+.1f} → {cls})")

        output = '\n'.join(lines)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"Saved to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == '__main__':
    main()
