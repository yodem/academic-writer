import React from 'react';
import {Frame} from './Frame';
import {C, p, rise, mono, sans, spectral, shadow, useScaled} from './theme';

const SOURCES = ['Primary text, critical edition', 'Monograph, chapters 3–5', 'Journal article (2019)', 'Archive letters, vol. 2'];
const THESES = ['The polemic concerned authority alone.', 'The polemic was not only about authority.', 'The polemic reflects a later editorial layer.'];
const CMD = '/academic-writer:write';
const ANSWER = 'The 1890s polemic over authority. English, please.';

const Check: React.FC<{on: number; size?: number}> = ({on, size = 26}) => (
  <span style={{display: 'inline-flex', width: size, height: size, borderRadius: 6, border: `1.5px solid ${on > 0.05 ? C.verified : C.ink2}`, background: on > 0.05 ? C.verifiedSoft : 'transparent', alignItems: 'center', justifyContent: 'center', flex: 'none'}}>
    <svg width={size - 8} height={size - 8} viewBox="0 0 16 16" fill="none" stroke={C.verified} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" style={{opacity: on}}>
      <path d="M3 8.5l3.2 3L13 4.5" />
    </svg>
  </span>
);

const Dots: React.FC<{f: number}> = ({f}) => (
  <span style={{display: 'inline-flex', gap: 5, alignItems: 'center'}}>
    {[0, 1, 2].map((i) => (
      <span key={i} style={{width: 7, height: 7, borderRadius: 7, background: C.indigo, opacity: 0.35 + 0.65 * Math.max(0, Math.sin((f - i * 4) / 5))}} />
    ))}
  </span>
);

const SideItem: React.FC<{label: string; active?: boolean; icon: React.ReactNode}> = ({label, active, icon}) => (
  <div style={{display: 'flex', alignItems: 'center', gap: 14, padding: '12px 16px', borderRadius: 8, fontSize: 25, fontWeight: active ? 500 : 400, color: active ? C.indigo : C.ink2, background: active ? C.indigoSoft : 'transparent'}}>
    {icon}{label}
  </div>
);

const ico = (d: string) => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={d} /></svg>
);

export const S2: React.FC<{dur: number}> = ({dur}) => {
  const f = useScaled(190, dur, 0.7, 1.1);
  const typed = Math.floor(Math.min(1, Math.max(0, (f - 26) / 24)) * CMD.length);
  const caret = f < 54 && Math.floor(f / 8) % 2 === 0;
  const ans = Math.floor(Math.min(1, Math.max(0, (f - 86) / 22)) * ANSWER.length);
  const sel = p(f, 174, 14);
  const bubble: React.CSSProperties = {borderRadius: 14, padding: '16px 22px', fontSize: 26, lineHeight: 1.35};
  return (
    <Frame n={2} dur={dur} headline="You bring the topic, the sources and the thesis.">
      <div style={{position: 'absolute', left: 0, top: -6, width: 1650, height: 660, display: 'flex', background: C.paper2, border: `1px solid ${C.rule}`, borderRadius: 14, boxShadow: shadow, overflow: 'hidden', ...rise(f, 6, 20, 12)}}>
        {/* sidebar */}
        <div style={{width: 250, borderRight: `1px solid ${C.rule}`, padding: '26px 16px', display: 'flex', flexDirection: 'column', gap: 6, background: C.paper}}>
          <SideItem active label="Cowork" icon={ico('M4 6h16M4 12h16M4 18h10')} />
          <SideItem label="Customize" icon={ico('M5 7h14M5 17h14M9 4v6M15 14v6')} />
        </div>
        {/* main */}
        <div style={{flex: 1, display: 'flex', flexDirection: 'column'}}>
          <div style={{height: 70, borderBottom: `1px solid ${C.rule}`, display: 'flex', alignItems: 'center', padding: '0 30px'}}>
            <span style={{display: 'inline-flex', alignItems: 'center', gap: 10, fontSize: 23, color: C.ink2, border: `1px solid ${C.rule}`, borderRadius: 999, padding: '7px 18px', background: C.paper}}>
              {ico('M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z')}
              Connected folder: <span style={{color: C.ink, fontWeight: 500}}>Polemic article</span>
            </span>
          </div>
          <div style={{flex: 1, display: 'flex'}}>
            {/* conversation */}
            <div style={{width: 700, padding: '26px 30px', display: 'flex', flexDirection: 'column', gap: 18}}>
              <div style={{alignSelf: 'flex-end', ...bubble, background: C.indigoSoft, border: `1px solid ${C.indigo}`, fontFamily: mono, fontSize: 25, color: C.ink, minWidth: 120, minHeight: 28, ...rise(f, 18, 12, 8)}}>
                {CMD.slice(0, typed)}
                <span style={{display: 'inline-block', width: 11, height: 24, background: caret ? C.indigo : 'transparent', verticalAlign: -4, marginLeft: 2}} />
              </div>
              <div style={{alignSelf: 'flex-start', maxWidth: 600, ...bubble, background: C.paper, border: `1px solid ${C.rule}`, color: C.ink, ...rise(f, 58, 16, 8)}}>
                <div style={{fontSize: 18, color: C.ink2, fontWeight: 500, marginBottom: 4}}>Claude</div>
                What would you like to write about, and in which language?
              </div>
              <div style={{alignSelf: 'flex-end', maxWidth: 540, ...bubble, background: C.indigoSoft, border: `1px solid ${C.indigo}`, color: C.ink, opacity: p(f, 82, 8)}}>
                {ANSWER.slice(0, ans)}
              </div>
            </div>
            {/* progress */}
            <div style={{flex: 1, borderLeft: `1px solid ${C.rule}`, padding: '24px 34px', background: C.paper, ...rise(f, 98, 18, 10)}}>
              <div style={{fontSize: 20, fontWeight: 500, letterSpacing: '0.04em', textTransform: 'uppercase', color: C.ink2, marginBottom: 14}}>Progress</div>
              <div style={{display: 'flex', alignItems: 'center', gap: 14, fontSize: 25, color: C.ink, marginBottom: 14, opacity: p(f, 102, 10)}}>
                <Check on={p(f, 106, 8)} /> Topic and language
              </div>
              <div style={{display: 'flex', alignItems: 'center', gap: 14, fontSize: 25, color: C.ink, fontWeight: 500, marginBottom: 8, opacity: p(f, 110, 10)}}>
                <Check on={p(f, 150, 8)} /> Sources
              </div>
              {SOURCES.map((s, i) => (
                <div key={s} style={{display: 'flex', alignItems: 'center', gap: 12, marginLeft: 40, marginBottom: 6, fontFamily: spectral, fontSize: 24, color: C.ink2, opacity: p(f, 114 + i * 8, 10)}}>
                  <Check size={20} on={p(f, 120 + i * 8, 8)} />{s}
                </div>
              ))}
              <div style={{display: 'flex', alignItems: 'center', gap: 14, fontSize: 25, color: C.ink, fontWeight: 500, margin: '14px 0 8px', opacity: p(f, 152, 10)}}>
                <span style={{width: 26, display: 'inline-flex', justifyContent: 'center'}}><Dots f={f} /></span> Thesis
              </div>
              {THESES.map((t, i) => {
                const on = i === 1 ? sel : 0;
                return (
                  <div key={t} style={{display: 'flex', alignItems: 'center', gap: 12, marginLeft: 28, marginBottom: 4, padding: '5px 12px', borderRadius: 8, fontFamily: spectral, fontSize: 24, color: C.ink,
                    background: on > 0.02 ? C.indigoSoft : 'transparent', border: `1px solid ${on > 0.02 ? C.indigo : 'transparent'}`, opacity: p(f, 156 + i * 6, 10)}}>
                    <span style={{fontFamily: mono, fontSize: 19, color: on > 0.02 ? C.indigo : C.ink2}}>{i + 1}</span>{t}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </Frame>
  );
};
