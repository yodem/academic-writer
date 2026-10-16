import React from 'react';
import {Frame, Chip} from './Frame';
import {C, p, rise, useScaled, sans, spectral, shadow} from './theme';

const Y = [0, 205, 410];
const P1 = 'The sources agree that the dispute first surfaces in correspondence, not in print.';
const P2a = 'The author concedes that the claim was “never raised in public”.';
const P2b = 'The author notes that the claim was raised only in private letters.';
const P3 = 'Later readers recast the procedural quarrel as a matter of doctrine.';
const FN = ['Monograph, p. 41', 'Archive letters, p. 91', 'Journal article, p. 88'];

export const S4: React.FC<{dur: number}> = ({dur}) => {
  const f = useScaled(224, dur, 0.7);
  const swap = p(f, 120, 24);
  const bad = f >= 85 && f < 130;
  const para = (y: number, i: number, start: number, body: React.ReactNode) => (
    <div style={{position: 'absolute', left: 0, top: y, width: 1040, height: 180, ...rise(f, start, 20)}}>
      <div style={{fontFamily: spectral, fontSize: 38, lineHeight: 1.4, color: C.ink}}>{body}</div>
    </div>
  );
  const sup = (s: string) => <sup style={{color: C.indigo, fontSize: 26, marginLeft: 2}}>{s}</sup>;
  const row = (y: number, start: number, fn: string, chip: React.ReactNode, mark: string) => (
    <div style={{position: 'absolute', left: 0, top: y, width: 560, ...rise(f, start, 16)}}>
      <div style={{fontFamily: spectral, fontSize: 28, color: C.ink2, marginBottom: 12}}><span style={{color: C.indigo}}>{mark}</span> {fn}</div>
      {chip}
    </div>
  );
  const ok = (start: number) => <Chip kind="ok" style={{opacity: p(f, start, 12), transform: `translateX(${(1 - p(f, start, 12)) * -8}px)`}}>verified</Chip>;
  return (
    <Frame n={4} dur={dur} headline="It drafts in your voice, and a separate auditor checks every footnote against the page.">
      {/* page */}
      <div style={{position: 'absolute', left: 0, top: 0, width: 1170, height: 660, background: C.paper2, border: `1px solid ${C.rule}`, borderRadius: 8, boxShadow: shadow}}>
        <div style={{position: 'absolute', left: 56, top: 40, width: 1050, height: 600}}>
          {para(Y[0], 0, 10, <>{P1}{sup('¹')}</>)}
          {para(Y[1], 1, 52, <>
            <span style={{position: 'relative'}}>
              <span style={{opacity: 1 - swap, display: swap >= 1 ? 'none' : 'inline', textDecoration: bad ? `underline wavy ${C.rejected}` : 'none', textUnderlineOffset: 6}}>{P2a}</span>
              <span style={{opacity: swap, display: swap <= 0 ? 'none' : 'inline'}}>{P2b}</span>
            </span>{sup('²')}</>)}
          {para(Y[2], 2, 176, <>{P3}{sup('³')}</>)}
        </div>
      </div>
      {/* auditor column */}
      <div style={{position: 'absolute', left: 1240, top: 0, width: 530, height: 660}}>
        <div style={{position: 'absolute', left: 0, top: -4, fontSize: 21, fontWeight: 500, letterSpacing: '0.04em', textTransform: 'uppercase', color: C.ink2, ...rise(f, 8, 14, 6)}}>Footnote check</div>
        <div style={{position: 'absolute', left: 0, top: 48, width: 540, height: 500}}>
          {row(Y[0] - 8 + 0, 24, FN[0], ok(40), '¹')}
          {f < 150
            ? row(Y[1] - 8, 74, FN[1].replace('91', '88'), f < 85 ? null : <Chip kind="bad" style={{opacity: p(f, 85, 12), transform: `translateX(${(1 - p(f, 85, 12)) * -8}px)`}}>rejected — quote not found on p. 88</Chip>, '²')
            : row(Y[1] - 8, 0, FN[1], ok(160), '²')}
          {row(Y[2] - 8, 196, FN[2], ok(210), '³')}
        </div>
      </div>
      {f >= 100 && f < 150 && (
        <div style={{position: 'absolute', left: 56, top: 690, fontSize: 24, color: C.ink2, fontFamily: sans, ...rise(f, 100, 14, 8)}}>
          Rewritten from the page, then checked again.
        </div>
      )}
    </Frame>
  );
};
