import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Frame} from './Frame';
import {C, p, rise, mono, sans, spectral, frank, shadow} from './theme';

export const S6: React.FC<{dur: number}> = ({dur}) => {
  const f = useCurrentFrame();
  return (
    <Frame n={6} dur={dur} headline="Free and open source. Hebrew and English.">
      <div style={{position: 'absolute', left: 0, top: 10, width: 840}}>
        <div style={{background: C.paper2, border: `1px solid ${C.rule}`, borderRadius: 12, boxShadow: shadow, padding: '38px 40px', ...rise(f, 12, 20)}}>
          <div style={{fontFamily: mono, fontSize: 31, color: C.ink}}><span style={{color: C.ink2}}>&gt; </span>/plugin install academic-writer@yodem</div>
        </div>
        <div style={{fontFamily: mono, fontSize: 36, color: C.indigo, marginTop: 56, ...rise(f, 42, 20)}}>yodem.github.io/academic-writer</div>
        <div style={{fontSize: 28, color: C.ink2, marginTop: 18, ...rise(f, 56, 20)}}>MIT licensed. Runs inside Claude Code.</div>
      </div>
      <div style={{position: 'absolute', left: 930, top: 10, width: 740, background: C.paper2, border: `1px solid ${C.rule}`, borderRadius: 8, boxShadow: shadow, padding: '40px 48px 32px', direction: 'rtl', textAlign: 'right', ...rise(f, 30, 22)}}>
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
