import { checkProfile } from '../lifecycle/check-profile.js';
import { loadFingerprint } from '../lifecycle/load-fingerprint.js';
import type { HookInput, HookResult } from '../types.js';

export const hooks: Record<string, (input: HookInput) => HookResult> = {
  'lifecycle/check-profile': checkProfile,
  'lifecycle/load-fingerprint': loadFingerprint,
};
