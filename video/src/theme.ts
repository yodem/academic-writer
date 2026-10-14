import {Easing, interpolate, useCurrentFrame} from 'remotion';
import {loadFont as loadSpectral} from '@remotion/google-fonts/Spectral';
import {loadFont as loadSans} from '@remotion/google-fonts/IBMPlexSans';
import {loadFont as loadMono} from '@remotion/google-fonts/IBMPlexMono';
import {loadFont as loadFrank} from '@remotion/google-fonts/FrankRuhlLibre';

export const spectral = loadSpectral('normal', {weights: ['400', '500'], subsets: ['latin']}).fontFamily;
export const sans = loadSans('normal', {weights: ['400', '500'], subsets: ['latin']}).fontFamily;
export const mono = loadMono('normal', {weights: ['400', '500'], subsets: ['latin']}).fontFamily;
export const frank = loadFrank('normal', {weights: ['500'], subsets: ['hebrew', 'latin']}).fontFamily;

export const C = {
  paper: 'oklch(0.978 0.004 250)',
  paper2: 'oklch(0.955 0.007 255)',
  ink: 'oklch(0.24 0.05 268)',
  ink2: 'oklch(0.42 0.035 265)',
  rule: 'oklch(0.88 0.012 260)',
  indigo: 'oklch(0.36 0.11 268)',
  indigoSoft: 'oklch(0.93 0.03 268)',
  verified: 'oklch(0.55 0.10 165)',
  verifiedText: 'oklch(0.40 0.09 165)',
  verifiedSoft: 'oklch(0.94 0.035 165)',
  rejected: 'oklch(0.56 0.17 32)',
  rejectedText: 'oklch(0.46 0.16 32)',
  rejectedSoft: 'oklch(0.95 0.03 32)',
};

export const ease = Easing.bezier(0.25, 1, 0.5, 1);

/** 0..1 eased progress from `start` over `dur` frames */
export const p = (frame: number, start: number, dur = 18) =>
  interpolate(frame, [start, start + dur], [0, 1], {easing: ease, extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

/** fade + small upward travel */
export const rise = (frame: number, start: number, dur = 18, travel = 14): React.CSSProperties => {
  const t = p(frame, start, dur);
  return {opacity: t, transform: `translateY(${(1 - t) * travel}px)`};
};

export const shadow = '0 1px 2px oklch(0.24 0.05 268 / 0.05), 0 12px 32px oklch(0.24 0.05 268 / 0.07)';

/** Frames of stillness kept at the end of every scene (0.6s) before the cut. */
export const HOLD = 18;

/** Scene-local time, stretched/compressed so all motion (authored to end at `motionEnd`) finishes HOLD frames before `dur`. */
export const useScaled = (motionEnd: number, dur: number, minK = 0.7, maxK = 1.1) => {
  const frame = useCurrentFrame();
  const k = Math.min(maxK, Math.max(minK, motionEnd / (dur - HOLD)));
  return frame * k;
};
