import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Frame} from './Frame';
import {C, p, rise, mono, sans, spectral, frank, shadow} from './theme';

export const S6: React.FC<{dur: number}> = ({dur}) => {
  const f = useCurrentFrame();
  return (
    <Frame n={6} dur={dur} headline="Free and open source. Hebrew and English.">
      <div style={{position: 'absolute', left: 0, top: 10, width: 860}}>
        <div style={{background: C.paper2, border: `1px solid ${C.rule}`, borderRadius: 12, boxShadow: shadow, padding: '30px 34px 32px', ...rise(f, 12, 20)}}>
          <div style={{fontSize: 21, fontWeight: 500, letterSpacing: '0.04em', textTransform: 'uppercase', color: C.ink2, marginBottom: 18}}>In Cowork</div>
          <div style={{display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '12px 10px', fontSize: 27, color: C.ink}}>
            {['Customize', 'Plugins', 'Add marketplace', 'yodem/academic-writer'].map((t, i) => (
              <span key={t} style={{display: 'inline-flex', alignItems: 'center', gap: 10, whiteSpace: 'nowrap'}}>
                {i > 0 && <span style={{color: C.indigo, fontSize: 27, ...rise(f, 20 + i * 8, 12, 4)}}>→</span>}
                <span style={{fontFamily: i === 3 ? mono : sans, fontSize: i === 3 ? 25 : 27, padding: '8px 16px', borderRadius: 8, background: i === 3 ? C.indigoSoft : C.paper, border: `1px solid ${i === 3 ? C.indigo : C.rule}`, color: i === 3 ? C.indigo : C.ink, ...rise(f, 20 + i * 8, 12, 6)}}>{t}</span>
              </span>
            ))}
          </div>
          <div style={{fontSize: 24, color: C.ink2, marginTop: 24, ...rise(f, 62, 16, 6)}}>Also works in Claude Code.</div>
        </div>
        <div style={{fontFamily: mono, fontSize: 36, color: C.indigo, marginTop: 50, ...rise(f, 72, 20)}}>yodem.github.io/academic-writer</div>
        <div style={{fontSize: 28, color: C.ink2, marginTop: 18, ...rise(f, 86, 20)}}>MIT licensed. Free and open source.</div>
      </div>
      <div style={{position: 'absolute', left: 950, top: 10, width: 720, background: C.paper2, border: `1px solid ${C.rule}`, borderRadius: 8, boxShadow: shadow, padding: '40px 48px 32px', direction: 'rtl', textAlign: 'right', ...rise(f, 30, 22)}}>
        <div style={{fontFamily: frank, fontWeight: 500, fontSize: 50, lineHeight: 1.5, color: C.ink}}>
          הטענה המרכזית של המאמר היא שהפולמוס לא נסב על שאלת הסמכות בלבד.<sup style={{color: C.indigo, fontSize: 28}}>1</sup>
        </div>
        <div style={{borderTop: `1px solid ${C.rule}`, marginTop: 34, paddingTop: 14, fontFamily: frank, fontSize: 30, color: C.ink2, ...rise(f, 70, 18, 8)}}>
          <sup>1</sup> שם, עמ' 41.
        </div>
      </div>
    </Frame>
  );
};
