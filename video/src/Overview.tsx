import React from 'react';
import {AbsoluteFill, Sequence} from 'remotion';
import {S1} from './S1';
import {S2} from './S2';
import {S3} from './S3';
import {S4} from './S4';
import {S5} from './S5';
import {S6} from './S6';

const FPS = 30;
export const SCENES: {from: number; dur: number; C: React.FC<{dur: number}>}[] = [
  {from: 0, dur: 5, C: S1},
  {from: 5, dur: 6, C: S2},
  {from: 11, dur: 7, C: S3},
  {from: 18, dur: 9, C: S4},
  {from: 27, dur: 7, C: S5},
  {from: 34, dur: 6, C: S6},
].map((s) => ({...s, from: s.from * FPS, dur: s.dur * FPS}));
export const TOTAL = 40 * FPS;

export const Overview: React.FC = () => (
  <AbsoluteFill style={{background: 'oklch(0.978 0.004 250)'}}>
    {SCENES.map((s, i) => (
      <Sequence key={i} from={s.from} durationInFrames={s.dur}>
        <s.C dur={s.dur} />
      </Sequence>
    ))}
  </AbsoluteFill>
);
