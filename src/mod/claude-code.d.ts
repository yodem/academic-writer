// Type stub for the `claude-code` module, only the slice register.tsx uses, so `npm run typecheck:mod` can check
// the mod without the engine's full type file (13k lines, not in this repo). Update it when register.tsx starts
// using more of the API; the engine's own `claude-code.d.ts` is the reference.
declare module 'claude-code' {
  export type PluginOptions = Record<string, unknown>
  type Timer = { cancel: () => void }
  export interface UiElement { readonly kind: 'element' }
  type Component = (props: { children?: unknown; [prop: string]: unknown }) => UiElement

  export interface EngineInterface {
    plugin: { root: string }
    session: { cwd: () => Promise<string> }
    clock: { now: () => Promise<number>; every: (ms: number, fn: () => void) => Timer }
    fs: {
      exists: (path: string) => Promise<boolean>
      read: (path: string) => Promise<string>
      list: (path: string) => Promise<Array<{ name: string; kind: string }>>
      stat: (path: string, options?: { resolve?: boolean }) => Promise<{ mtimeMs?: number }>
    }
    command: { register: (spec: { name: string; description: string }) => Promise<unknown> }
    ui: {
      invalidate: (event: 'ui.render') => void
      open: (spec: { id: string; title: string }) => Promise<{ isPlaced: boolean }>
      resolve: (event: unknown) => { Box: Component; Text: Component }
    }
  }

  type Next<E> = (event: E) => Promise<E> | E
  type Handler = ($: EngineInterface, event: { cwd: string }, next: Next<{ cwd: string }>) => unknown
  export type On = {
    (event: 'session.start' | 'turn.complete' | 'agent.spawn', handler: Handler): unknown
    (event: 'command.run', filter: { command: string }, handler: ($: EngineInterface) => unknown): unknown
    (event: 'ui.render', filter: { component: string; requestId: string }, handler: ($: EngineInterface, event: unknown) => unknown): unknown
  }
  export type Register = (on: On, options: PluginOptions) => unknown
}

declare namespace JSX {
  type Element = import('claude-code').UiElement
  interface ElementChildrenAttribute { children: unknown }
  interface IntrinsicAttributes { [prop: string]: unknown }
}
