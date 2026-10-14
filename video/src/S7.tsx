import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
import {C, p, rise, mono, spectral} from './theme';

/** End card: elements settle by ~1s, hold, then fade to paper over the last 0.8s. */
export const S7: React.FC<{dur: number}> = ({dur}) => {
  const f = useCurrentFrame();
  const fade = interpolate(f, [dur - 24, dur - 1], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const open = interpolate(f, [0, 6], [0, 1], {extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill style={{background: C.paper}}>
      <AbsoluteFill style={{opacity: Math.min(fade, open), alignItems: 'center', justifyContent: 'center'}}>
        <div style={{textAlign: 'center'}}>
          <div style={{fontFamily: spectral, fontWeight: 500, fontSize: 132, lineHeight: 1.02, letterSpacing: '-0.015em', color: C.ink, ...rise(f, 0, 20, 16)}}>
            Academic Writer<span style={{fontSize: 58, verticalAlign: 'super', color: C.indigo, marginLeft: 6}}>¹</span>
          </div>
          <div style={{height: 1, background: C.indigo, width: 160 * p(f, 4, 20), margin: '38px auto 34px'}} />
          <div style={{fontFamily: spectral, fontWeight: 400, fontSize: 52, color: C.ink2, ...rise(f, 10, 20, 12)}}>
            Your argument. Your sources. Your voice.
          </div>
          <div style={{fontFamily: mono, fontSize: 36, color: C.indigo, marginTop: 52, ...rise(f, 18, 12, 8)}}>
            yodem.github.io/academic-writer
          </div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
