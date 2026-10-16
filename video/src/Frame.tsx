import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {C, ease, p, rise, spectral, sans} from './theme';

const SUP = ['¹', '²', '³', '⁴', '⁵', '⁶'];

/** Shared scene chrome: paper, margin rule with footnote marker, caption headline, scene fade. */
export const Frame: React.FC<{n: number; dur: number; headline: React.ReactNode; children?: React.ReactNode; scale?: number}> = ({
  n, dur, headline, children, scale = 1,
}) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 8, dur - 8, dur], [0, 1, 1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const rule = p(frame, 0, 30);
  return (
    <AbsoluteFill style={{background: C.paper, opacity}}>
      {/* margin rule */}
      <div style={{position: 'absolute', left: 84, top: 70, width: 1, height: 940 * rule, background: C.rule}} />
      <div style={{position: 'absolute', left: 52, top: 96, width: 24, textAlign: 'right', fontFamily: spectral, fontSize: 30, color: C.indigo, ...rise(frame, 4, 16, 6)}}>
        {SUP[n - 1]}
      </div>
      <div style={{position: 'absolute', left: 150, top: 82, width: 1500, textWrap: 'balance' as const, fontFamily: spectral, fontWeight: 500, fontSize: 56, lineHeight: 1.16, letterSpacing: '-0.01em', color: C.ink, ...rise(frame, 4, 20)}}>
        {headline}
      </div>
      <div style={{position: 'absolute', left: 150, right: 120, top: 330, bottom: 80, fontFamily: sans, transform: `scale(${scale})`, transformOrigin: 'top left'}}>{children}</div>
    </AbsoluteFill>
  );
};

export const Chip: React.FC<{kind: 'ok' | 'bad'; children: React.ReactNode; style?: React.CSSProperties}> = ({kind, children, style}) => (
  <span style={{
    display: 'inline-flex', alignItems: 'center', gap: 8, fontFamily: sans, fontWeight: 500, fontSize: 23,
    padding: '7px 16px', borderRadius: 999,
    color: kind === 'ok' ? C.verifiedText : C.rejectedText,
    background: kind === 'ok' ? C.verifiedSoft : C.rejectedSoft,
    border: `1px solid ${kind === 'ok' ? C.verified : C.rejected}`,
    whiteSpace: 'nowrap', ...style,
  }}>
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      {kind === 'ok' ? <path d="M3 8.5l3.2 3L13 4.5" /> : <path d="M4 4l8 8M12 4l-8 8" />}
    </svg>
    {children}
  </span>
);
