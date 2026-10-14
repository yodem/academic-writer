import React from 'react';
import {Frame} from './Frame';
import {C, p, rise, useScaled, mono, sans, spectral, shadow} from './theme';

const X = [0, 620, 1240];
const W = 460;
const H = 168;
const Y = [40, 250, 460];
const ARGS = ['The dispute began as a question of procedure.', 'Authority was contested in private first.', 'Later readers recast it as doctrine.'];
const QUOTES = ['“…raised only in letters, never from the pulpit.”', '“…the question of who may decide.”', '“…a matter of doctrine, not of rule.”'];
const PAGES = ['Monograph, p. 41', 'Archive letters, p. 12', 'Journal article, p. 88'];
// [argIndex, quoteIndex] and [quoteIndex, pageIndex]
const L1: [number, number][] = [[0, 0], [1, 0], [1, 1], [2, 2]];
const L2: [number, number][] = [[0, 0], [1, 1], [2, 2]];

const Line: React.FC<{x1: number; y1: number; x2: number; y2: number; prog: number}> = ({x1, y1, x2, y2, prog}) => {
  const mx = (x1 + x2) / 2;
  return <path d={`M${x1} ${y1} C${mx} ${y1} ${mx} ${y2} ${x2} ${y2}`} fill="none" stroke={C.indigo} strokeWidth={1.5} pathLength={1} strokeDasharray={1} strokeDashoffset={1 - prog} opacity={0.7} />;
};

export const S3: React.FC<{dur: number}> = ({dur}) => {
  const f = useScaled(156, dur, 0.7);
  const col = (c: number, i: number, text: string, kind: 'a' | 'q' | 'p', start: number) => (
    <div key={`${c}${i}`} style={{position: 'absolute', left: X[c], top: Y[i], width: W, height: H, boxSizing: 'border-box', padding: '20px 24px', borderRadius: 8, background: kind === 'p' ? C.indigoSoft : C.paper2, border: `1px solid ${kind === 'p' ? C.indigo : C.rule}`, boxShadow: kind === 'p' ? 'none' : shadow,
      display: 'flex', alignItems: 'center', fontFamily: kind === 'p' ? mono : spectral, fontSize: kind === 'p' ? 30 : 33, lineHeight: 1.25, fontStyle: kind === 'q' ? 'italic' : 'normal', color: kind === 'p' ? C.indigo : C.ink, fontWeight: kind === 'p' ? 500 : 400, ...rise(f, start + i * 8, 18)}}>
      {text}
    </div>
  );
  const label = (c: number, t: string, start: number) => (
    <div style={{position: 'absolute', left: X[c], top: -18, fontSize: 21, fontWeight: 500, color: C.ink2, letterSpacing: '0.04em', textTransform: 'uppercase', ...rise(f, start, 14, 6)}}>{t}</div>
  );
  return (
    <Frame n={3} dur={dur} headline="It maps the evidence in your sources: arguments, quotations, page numbers.">
      <div style={{position: 'absolute', left: 0, top: 20, width: 1800, height: 700}}>
        {label(0, 'Arguments', 8)}{label(1, 'Quotations', 40)}{label(2, 'Page numbers', 80)}
        <svg width={1800} height={700} style={{position: 'absolute', left: 0, top: 0, overflow: 'visible'}}>
          {L1.map(([a, q], i) => <Line key={`a${i}`} x1={X[0] + W} y1={Y[a] + H / 2} x2={X[1]} y2={Y[q] + H / 2} prog={p(f, 62 + i * 8, 26)} />)}
          {L2.map(([q, g], i) => <Line key={`b${i}`} x1={X[1] + W} y1={Y[q] + H / 2} x2={X[2]} y2={Y[g] + H / 2} prog={p(f, 108 + i * 10, 26)} />)}
        </svg>
        {ARGS.map((t, i) => col(0, i, t, 'a', 12))}
        {QUOTES.map((t, i) => col(1, i, t, 'q', 44))}
        {PAGES.map((t, i) => col(2, i, t, 'p', 84))}
      </div>
    </Frame>
  );
};
