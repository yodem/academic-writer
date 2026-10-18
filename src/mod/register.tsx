// academic-writer activity pane: never name a local `h` in this file. Every JSX tag compiles to a call of
// `h`, the JSX factory global, and a local `h` breaks the first draw.
//
// Read-only: it reads runs/<id>/activity.jsonl with `$.fs` and never writes or submits a prompt. No model call.
// The activity file is re-read on a 2 s clock tick only while a run is active; engine events (turn.complete,
// agent.spawn) are only triggers to re-read.
import type { EngineInterface as Engine, Register } from 'claude-code'
import { type PaneView, parseEvents, viewOf } from './model.ts'

const PANE_ID = 'aw-activity'
const COMMAND = 'watch'
const TICK_MS = 2000
const DEFAULT_MAX_AGE_MIN = 360

type Timer = { cancel: () => void }

const STATE_GLYPH: Record<string, string> = {
  done: '✓', current: '◐', todo: '·', drafted: '✎', passed: '✓', rejected: '✗', redrafted: '⟳',
}

function clock(totalS: number): string {
  const m = Math.floor(totalS / 60)
  const s = totalS % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

let paneEnabled = true
let view: PaneView | undefined
let active = false
let timer: Timer | undefined

async function refresh($: Engine): Promise<void> {
  try {
    const cwd = await $.session.cwd()
    const root = `${cwd}/.academic-helper`
    if (!(await $.fs.exists(`${root}/profile.md`)) || !(await $.fs.exists(`${root}/runs`))) { setActive($, false, undefined); return }
    const now = await $.clock.now()
    let running: { text: string; mtime: number } | undefined
    let finished: { text: string; mtime: number } | undefined
    for (const entry of await $.fs.list(`${root}/runs`)) {
      if (entry.kind !== 'dir') continue
      const file = `${root}/runs/${entry.name}/activity.jsonl`
      try {
        const stat = await $.fs.stat(file, { resolve: false })
        const mtime = stat.mtimeMs ?? 0
        if (now - mtime > DEFAULT_MAX_AGE_MIN * 60_000) continue
        const text = await $.fs.read(file)
        const kinds = parseEvents(text).map((ev) => ev.kind)
        if (!kinds.includes('run_start')) continue
        if (kinds.includes('run_end')) { if (!finished || mtime > finished.mtime) finished = { text, mtime } }
        else if (!running || mtime > running.mtime) running = { text, mtime }
      } catch {
        // a run folder without an activity file
      }
    }
    const pick = running ?? finished
    if (!pick) { setActive($, false, undefined); return }
    setActive($, running !== undefined, viewOf(parseEvents(pick.text), new Date(now)))
  } catch {
    // unreadable: keep the last view, never crash the session
  }
}

function setActive($: Engine, running: boolean, next: PaneView | undefined): void {
  view = next
  if (running && !timer) timer = $.clock.every(TICK_MS, () => { void refresh($) })
  if (!running && timer) { timer.cancel(); timer = undefined }
  active = running
  $.ui.invalidate('ui.render')
}

export const register: Register = (on, options) => {
  paneEnabled = options['activity_pane'] !== false
  view = undefined
  active = false
  timer = undefined

  on('session.start', async ($, e, next) => {
    await $.command.register({ name: COMMAND, description: 'Show the live Academic Writer activity pane' })
    if (paneEnabled && (await $.fs.exists(`${e.cwd}/.academic-helper/profile.md`).catch(() => false))) {
      // unasked: the engine places it only in a wide terminal (144+ columns)
      void $.ui.open({ id: PANE_ID, title: 'Academic Writer' })
      void refresh($)
    }
    return next(e)
  })

  on('command.run', { command: COMMAND }, async ($) => {
    const opened = await $.ui.open({ id: PANE_ID, title: 'Academic Writer' })
    await refresh($)
    return { text: opened.isPlaced ? 'The activity pane is open.' : 'The terminal is too narrow for the pane; run `aw activity show --latest` for a status line.' }
  })

  on('turn.complete', async ($, e, next) => {
    void refresh($)
    return next(e)
  })

  on('agent.spawn', async ($, e, next) => {
    void refresh($)
    return next(e)
  })

  on('ui.render', { component: 'Pane', requestId: PANE_ID }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    if (!view || view.steps.length === 0) {
      return <Text dimColor>No Academic Writer run yet. Start one with /academic-writer:write.</Text>
    }
    const v = view
    return (
      <Box flexDirection="column">
        <Text bold>{v.flow} {active ? '' : '(done)'}  {clock(v.elapsedS)}</Text>
        {v.steps.map((s) => (
          <Text dimColor={s.state === 'todo'}>{STATE_GLYPH[s.state]} {s.id}{s.state === 'current' ? ' ...' : ''}</Text>
        ))}
        {v.units.length > 0 && <Text dimColor>sections</Text>}
        {v.units.map((u) => (
          <Text>{STATE_GLYPH[u.state]} {u.id}</Text>
        ))}
        {v.agent && <Text>agent: {v.agent}</Text>}
        {v.rejections.map((r) => (
          <Text>✗ {r.unit}: {r.reason}</Text>
        ))}
      </Box>
    )
  })
}
