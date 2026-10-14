import React from 'react';
import {AbsoluteFill, Sequence} from 'remotion';
import {S1} from './S1';
import {S2} from './S2';
import {S3} from './S3';
import {S4} from './S4';
import {S5} from './S5';
import {S6} from './S6';
import {S7} from './S7';

const FPS = 30;
// Scene lengths in frames: narration clip + ~0.8s of air (see audio/ build notes). Narration starts 3 frames into each scene.
const DURS = [216, 222, 234, 231, 255, 275, 222];
const COMPS: React.FC<{dur: number}>[] = [S1, S2, S3, S4, S5, S6, S7];
export const SCENES = DURS.map((dur, i) => ({
  from: DURS.slice(0, i).reduce((a, b) => a + b, 0),
  dur,
  C: COMPS[i],
}));
export const TOTAL = DURS.reduce((a, b) => a + b, 0);
void FPS;

export const Overview: React.FC = () => (
  <AbsoluteFill style={{background: 'oklch(0.978 0.004 250)'}}>
    {SCENES.map((s, i) => (
      <Sequence key={i} from={s.from} durationInFrames={s.dur}>
        <s.C dur={s.dur} />
      </Sequence>
    ))}
  </AbsoluteFill>
);
