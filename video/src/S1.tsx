import React from 'react';
import {AbsoluteFill, Img, staticFile, useCurrentFrame, interpolate} from 'remotion';
import {C, p, rise, ease, HOLD, spectral, sans} from './theme';

export const S1: React.FC<{dur: number}> = ({dur}) => {
  const f = useCurrentFrame();
  const scale = interpolate(f, [0, dur - HOLD], [1.0, 1.04], {easing: ease, extrapolateRight: 'clamp'});
  const opacity = interpolate(f, [0, 10, dur - 8, dur], [0, 1, 1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill style={{background: C.paper, opacity}}>
      <AbsoluteFill style={{opacity: 0.92 * p(f, 0, 36), transform: `scale(${scale})`, transformOrigin: '75% 40%'}}>
        <Img src={staticFile('hero-desk-lg.webp')} style={{width: 1920, height: 1080}} />
      </AbsoluteFill>
      <div style={{position: 'absolute', left: 84, top: 70, width: 1, height: 940 * p(f, 0, 30), background: C.rule}} />
      <div style={{position: 'absolute', left: 150, top: 310, width: 900}}>
        <div style={{fontFamily: spectral, fontWeight: 500, fontSize: 132, lineHeight: 1.02, letterSpacing: '-0.015em', color: C.ink, ...rise(f, 8, 24, 18)}}>
          Academic Writer<span style={{fontSize: 58, verticalAlign: 'super', color: C.indigo, marginLeft: 6}}>¹</span>
        </div>
        <div style={{height: 1, background: C.indigo, width: 160 * p(f, 30, 24), margin: '36px 0 32px'}} />
        <div style={{fontFamily: spectral, fontWeight: 400, fontSize: 42, lineHeight: 1.28, color: C.ink2, width: 620, ...rise(f, 34, 22, 14)}}>
          From a rough idea to a footnoted article you can defend.
        </div>
      </div>
    </AbsoluteFill>
  );
};
