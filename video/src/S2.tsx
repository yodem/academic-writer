import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Frame} from './Frame';
import {C, p, rise, mono, sans, spectral, shadow} from './theme';

const SOURCES = ['Primary text, critical edition', 'Monograph, chapters 3–5', 'Journal article (2019)', 'Archive letters, vol. 2'];
const THESES = ['The polemic concerned authority alone.', 'The polemic was not only about authority.', 'The polemic reflects a later editorial layer.'];
const CMD = '/academic-writer:write';

const Check: React.FC<{on: number}> = ({on}) => (
  <span style={{display: 'inline-flex', width: 28, height: 28, borderRadius: 6, border: `1.5px solid ${on > 0.05 ? C.verified : C.ink2}`, background: on > 0.05 ? C.verifiedSoft : 'transparent', alignItems: 'center', justifyContent: 'center', flex: 'none'}}>
    <svg width="18" height="18" viewBox="0 0 16 16" fill="none" stroke={C.verified} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" style={{opacity: on}}>
      <path d="M3 8.5l3.2 3L13 4.5" />
    </svg>
  </span>
);

export const S2: React.FC<{dur: number}> = ({dur}) => {
  const f = useCurrentFrame();
  const typed = Math.floor(Math.min(1, Math.max(0, (f - 26) / 36)) * CMD.length);
  const caret = f < 70 && Math.floor(f / 8) % 2 === 0;
  const sel = p(f, 142, 14);
  return (
    <Frame n={2} dur={dur} scale={1.1} headline="You bring the topic, the sources and the thesis.">
      <div style={{width: 1500, background: C.paper2, border: `1px solid ${C.rule}`, borderRadius: 12, boxShadow: shadow, padding: '32px 44px 40px', ...rise(f, 10, 20, 12)}}>
        <div style={{fontFamily: mono, fontSize: 30, color: C.ink, height: 44}}>
          <span style={{color: C.ink2}}>&gt; </span>{CMD.slice(0, typed)}
          <span style={{display: 'inline-block', width: 14, height: 30, background: caret ? C.indigo : 'transparent', verticalAlign: -5, marginLeft: 2}} />
        </div>
        <div style={{height: 1, background: C.rule, margin: '20px 0 28px'}} />
        <div style={{display: 'flex', gap: 80}}>
          <div style={{flex: 1, ...rise(f, 68, 18)}}>
            <div style={{fontSize: 22, color: C.ink2, marginBottom: 20, fontWeight: 500}}>Choose your sources</div>
            {SOURCES.map((s, i) => (
              <div key={s} style={{display: 'flex', alignItems: 'center', gap: 16, marginBottom: 18, fontSize: 27, color: C.ink}}>
                <Check on={p(f, 84 + i * 12, 10)} />
                <span style={{fontFamily: spectral, fontSize: 30}}>{s}</span>
              </div>
            ))}
          </div>
          <div style={{width: 1, background: C.rule}} />
          <div style={{flex: 1.05, ...rise(f, 112, 18)}}>
            <div style={{fontSize: 22, color: C.ink2, marginBottom: 20, fontWeight: 500}}>Your thesis: pick, adjust or write your own</div>
            {THESES.map((t, i) => {
              const on = i === 1 ? sel : 0;
              return (
                <div key={t} style={{display: 'flex', alignItems: 'center', gap: 16, marginBottom: 14, padding: '10px 16px', borderRadius: 8, fontFamily: spectral, fontSize: 30, color: C.ink,
                  background: on > 0.02 ? C.indigoSoft : 'transparent', border: `1px solid ${on > 0.02 ? C.indigo : 'transparent'}`}}>
                  <span style={{fontFamily: mono, fontSize: 22, color: on > 0.02 ? C.indigo : C.ink2}}>{i + 1}</span>
                  {t}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </Frame>
  );
};
