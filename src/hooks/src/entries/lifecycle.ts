import { sessionDashboard } from '../lifecycle/session-dashboard.js';
import { sessionEndLog } from '../lifecycle/session-end-log.js';
import type { HookInput, HookResult } from '../types.js';

export const hooks: Record<string, (input: HookInput) => HookResult> = {
  'lifecycle/session-dashboard': sessionDashboard,
  'lifecycle/session-end-log': sessionEndLog,
};
