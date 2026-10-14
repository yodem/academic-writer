import React from 'react';
import {Frame} from './Frame';
import {C, p, rise, useScaled, mono, sans, spectral, shadow} from './theme';

const COMMENTS: {y: number; text: string; at: number}[] = [
  {y: 50, text: 'Tighten this sentence.', at: 30},
  {y: 196, text: 'Name the letter here.', at: 48},
  {y: 342, text: 'Is this the strongest quote?', at: 66},
];

export const S5: React.FC<{dur: number}> = ({dur}) => {
  const f = useScaled(146, dur, 0.7);
  const done = p(f, 128, 16);
  return (
    <Frame n={5} dur={dur} headline="You get a Word file. Comment on it like any draft; it folds your comments back in.">
      {/* docx page */}
      <div style={{position: 'absolute', left: 0, top: -6, width: 860, height: 640, background: C.paper2, border: `1px solid ${C.rule}`, borderRadius: 6, boxShadow: shadow, overflow: 'hidden', ...rise(f, 8, 22, 12)}}>
        <div style={{height: 44, borderBottom: `1px solid ${C.rule}`, display: 'flex', alignItems: 'center', padding: '0 24px', fontFamily: mono, fontSize: 19, color: C.ink2}}>article-draft.docx</div>
        <div style={{padding: '30px 64px 0', fontFamily: spectral, color: C.ink}}>
          <div style={{fontSize: 34, fontWeight: 500, marginBottom: 22}}>The Quarrel Over Who May Decide</div>
          <div style={{fontSize: 29, lineHeight: 1.55}}>
            The sources agree that the dispute first surfaces in correspondence, not in print.<sup style={{color: C.indigo, fontSize: 18}}>1</sup>{' '}
            The author notes that the claim was raised only in private letters.<sup style={{color: C.indigo, fontSize: 18}}>2</sup>{' '}
            Later readers recast the procedural quarrel as a matter of doctrine.<sup style={{color: C.indigo, fontSize: 18}}>3</sup>
          </div>
        </div>
        <div style={{position: 'absolute', left: 64, right: 64, bottom: 28, borderTop: `1px solid ${C.rule}`, paddingTop: 12, fontFamily: spectral, fontSize: 21, lineHeight: 1.5, color: C.ink2}}>
          <div><sup>1</sup> Monograph, p. 41.</div>
          <div><sup>2</sup> Archive letters, p. 91.</div>
          <div><sup>3</sup> Journal article, p. 88.</div>
        </div>
      </div>
      {/* margin comments */}
      <div style={{position: 'absolute', left: 905, top: 0, width: 410}}>
        {COMMENTS.map((c, i) => (
          <div key={i} style={{position: 'absolute', top: c.y + 20, left: 0, width: 410, ...rise(f, c.at, 18, 12)}}>
            <div style={{position: 'absolute', left: -40, top: 24, width: 40, height: 1, background: C.indigo, opacity: 0.6}} />
            <div style={{boxSizing: 'border-box', background: C.indigoSoft, border: `1px solid ${C.indigo}`, borderRadius: 8, padding: '14px 18px', fontSize: 25, color: C.ink, lineHeight: 1.3}}>
              <div style={{fontSize: 17, color: C.indigo, fontWeight: 500, marginBottom: 4}}>You</div>
              {c.text}
            </div>
          </div>
        ))}
      </div>
      {/* confirmation */}
      <div style={{position: 'absolute', left: 1345, top: 170, width: 330, opacity: done, transform: `translateY(${(1 - done) * 14}px)`}}>
        <div style={{fontFamily: mono, fontSize: 21, color: C.ink2, marginBottom: 14}}>/academic-writer:revise</div>
        <div style={{background: C.verifiedSoft, border: `1px solid ${C.verified}`, borderRadius: 10, padding: '22px 24px', color: C.verifiedText, fontSize: 28, lineHeight: 1.3, fontWeight: 500, boxShadow: shadow}}>
          <svg width="30" height="30" viewBox="0 0 16 16" fill="none" stroke={C.verified} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{display: 'block', marginBottom: 10}}><path d="M3 8.5l3.2 3L13 4.5" /></svg>
          3 changes confirmed — new draft saved
          <div style={{fontFamily: mono, fontWeight: 400, fontSize: 20, color: C.ink2, marginTop: 12}}>article-draft-v2.docx</div>
        </div>
      </div>
    </Frame>
  );
};
