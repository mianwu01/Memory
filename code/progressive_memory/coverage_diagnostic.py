"""Post-run gold-literal coverage diagnostic; never used by selectors or actors."""
import json
from pathlib import Path
from .collect import references
from .corpus import Corpus
from .discovery import trajectories
from .runtime import normalize,save
from .audit import document_ids

base=Path('results/development/progressive_search');corpus=Corpus('/tmp/hm3-progressive-search-20260922.sqlite');refs=references();rows=[]
for tr in trajectories(base/'dev_v2',0,10):
    answer=normalize(refs[tr['case']]);visible=set();read_ids=set()
    for event in tr['events']:
        read_ids.update(document_ids(event))
        for r in event['source_reads']:
            docs=r.get('results',[]) if r['tool']=='search' else ([r['result']] if r.get('result') else [])
            visible.update(d['docid'] for d in docs if answer in normalize(d['text']))
    original=[]
    for docid in sorted(read_ids):
        text=corpus.db.execute('SELECT text FROM docs WHERE docid=?',(docid,)).fetchone()
        if text and answer in normalize(text['text']):original.append(docid)
    rows.append(dict(case=tr['case'],reference=refs[tr['case']],literal_in_final_memory=answer in normalize(tr['final_memory']),
                     visible_matching_docids=sorted(visible),untruncated_matching_docids=original,unique_read_docs=len(read_ids),
                     note='Literal occurrence is not sufficient evidence for all question constraints; multi-field/alias answers can be absent as contiguous text'))
save(base/'reference_literal_coverage.json',dict(source=Path(__file__).read_text(),rows=rows))
for r in rows:print(r['case'],r['literal_in_final_memory'],len(r['visible_matching_docids']),len(r['untruncated_matching_docids']),flush=True)
