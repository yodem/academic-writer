import { notifyStop } from '../lifecycle/notify-stop.js';
import { sessionDashboard } from '../lifecycle/session-dashboard.js';
import { sessionEndLog } from '../lifecycle/session-end-log.js';
import { subagentStart } from '../lifecycle/subagent-start.js';
import { voicePull } from '../lifecycle/voice-pull.js';
import type { HookInput, HookResult } from '../types.js';

export const hooks: Record<string, (input: HookInput) => HookResult> = {
  'lifecycle/notify-stop': notifyStop,
  'lifecycle/session-dashboard': sessionDashboard,
  'lifecycle/session-end-log': sessionEndLog,
  'lifecycle/subagent-start': subagentStart,
  'lifecycle/voice-pull': voicePull,
};
