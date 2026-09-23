#!/usr/bin/env python3
"""Deterministic defect and Jev agreement reports for plugin development."""
import argparse, glob, json, re
from collections import defaultdict
from pathlib import Path
CONFIG=json.loads((Path(__file__).resolve().parents[1]/'src/thresholds.json').read_text(encoding='utf8'))['awImprove']

def tokens(s):
    return set(re.findall(r"[\w']+", s.casefold()))
def similar(a, b):
    union = a | b
    return bool(union) and len(a & b) / len(union) >= CONFIG['defectSimilarity']
def load(path):
    out=[]
    for filename in glob.glob(path):
        try:
            with open(filename, encoding='utf8') as f:
                for line in f:
                    if line.strip(): out.append(json.loads(line))
        except FileNotFoundError: pass
    return out
def cluster(rows):
    groups=[]
    for row in rows:
        defect=row.get('authorWords', row.get('item', ''))
        if isinstance(defect, dict): defect=json.dumps(defect, ensure_ascii=False, sort_keys=True)
        words=tokens(str(defect)); step=row.get('step', 'unknown')
        group=next((g for g in groups if g['step']==step and similar(words,g['_tokens'])),None)
        if group is None:
            group={'key':step+' '+ ' '.join(sorted(words)), 'step':step, '_tokens':words,'count':0,'examples':[],'firstSeen':row.get('ts',''),'lastSeen':row.get('ts','')}; groups.append(group)
        group['count']+=1
        if len(group['examples'])<CONFIG['maxExamples']: group['examples'].append(defect)
        dates=[x for x in (group['firstSeen'],row.get('ts','')) if x]
        if dates: group['firstSeen']=min(dates);group['lastSeen']=max(dates)
    return [{k:v for k,v in g.items() if k!='_tokens'} for g in groups]
def jev_report(rows, labels):
    points=defaultdict(list)
    label_index={(r.get('point'),r.get('changeId',r.get('itemId'))):r.get('label') for r in labels if r.get('label')}
    for r in rows:
        label=r.get('label') or label_index.get((r.get('point'),r.get('changeId',r.get('itemId'))))
        answer=r.get('jevAnswer',r.get('answer'))
        if r.get('point') and label is not None and answer is not None:
            points[r['point']].append(answer == label)
    roster=CONFIG['jevRoster']
    return {p:{'labels':len(v),'agreement':sum(v)/len(v),'instability':0 if len(v)<2 else 1-max(sum(v),len(v)-sum(v))/len(v),'recommend':'promote' if len(v)>=roster['labels'] and sum(v)/len(v)>=roster['agreement'] and (0 if len(v)<2 else 1-max(sum(v),len(v)-sum(v))/len(v))<=roster['instability'] else 'hold'} for p,v in points.items()}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--ledger',required=True);ap.add_argument('--runs',default='');ap.add_argument('--json',action='store_true');ap.add_argument('--jev',action='store_true');a=ap.parse_args()
    rows=load(a.ledger)
    if a.runs: rows+=load(a.runs)
    labels=[]
    if a.jev:
        ledger_path=Path(a.ledger)
        labels=load(str(ledger_path.parent.parent/'labels'/'*.jsonl'))
    result={'agreement':jev_report(rows,labels)} if a.jev else {'clusters':cluster(rows)}
    print(json.dumps(result,ensure_ascii=False,indent=None if a.json else 2))
if __name__=='__main__': main()
