"""Offline ledger/input/provenance integrity and preservation verification."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
from .runtime import digest,save
from .status import preservation

base=Path('results/development/progressive_search');errors=[];models=Counter();responses=attempts=0;unresolved=[]
completeness={}
for filename,expected in [('evaluation_dev/results.json',160),('evaluation_rewired_dev/results.json',50),('audit_dev/results.json',105),('audit_evidence_only_dev/results.json',15)]:
    path=base/filename
    if not path.exists():
        errors.append(dict(file=str(path),problem='required_results_missing'));continue
    data=json.loads(path.read_text());rows=data['rows'];completeness[filename]=len(rows)
    if len(rows)!=expected:errors.append(dict(file=str(path),problem='required_row_count',actual=len(rows),expected=expected))
    if filename.startswith('evaluation'):
        identities=[(r['case'],r['method']) for r in rows]
        for method in {r['method'] for r in rows}:
            if {r['case'] for r in rows if r['method']==method}!=set(range(10)):
                errors.append(dict(file=str(path),problem='missing_frozen_case',method=method))
    else:
        identities=[(r['case'],r.get('condition','evidence_only'),r['repeat']) for r in rows]
        if {r['case'] for r in rows}!={0,1,2,6,9}:errors.append(dict(file=str(path),problem='audit_case_set_changed'))
    if len(set(identities))!=len(identities):errors.append(dict(file=str(path),problem='duplicate_result_row'))
    for row in rows:
        if 'returned_model' in row and row['returned_model'].casefold()!='deepseek-v4-flash-0731':errors.append(dict(file=str(path),problem='result_model_drift'))
        if not row.get('prompt_sha256'):errors.append(dict(file=str(path),problem='missing_result_input_identity'))
evaluation=base/'evaluation_dev/results.json'
if evaluation.exists():
    bykey={(r['case'],r['method']):r for r in json.loads(evaluation.read_text())['rows']}
    for case in range(10):
        for method in ['topic_only','wrong_17','wrong_29','wrong_43']:
            a=bykey.get((case,'discovered'));b=bykey.get((case,method))
            if a and b and (a['prompt_sha256']!=b['prompt_sha256'] or a['correct']!=b['correct']):errors.append(dict(problem='expected_identical_input_or_shared_result_mismatch',case=case,method=method))
input_cache={}
for ledger in sorted(base.rglob('ledger.jsonl')):
    directory=ledger.parent
    rows=[json.loads(s) for s in ledger.read_text().splitlines()]
    intents=[json.loads(s) for s in (directory/'requests.jsonl').read_text().splitlines()]
    intentions={(r['job_id'],r['attempt']):r for r in intents};finished=set();seen=set();attempts+=len(intents)
    for r in rows:
        ident=(r['job_id'],r['attempt']);finished.add(ident)
        if ident not in intentions:errors.append(dict(file=str(ledger),problem='result_without_intent'))
        path=directory/'inputs'/f"{r['prompt_sha256']}.json"
        if path not in input_cache:
            req=json.loads(path.read_text());input_cache[path]=req
            if digest(req)!=r['prompt_sha256']:errors.append(dict(file=str(path),problem='input_hash_mismatch'))
            if req.get('model')!='deepseek-v4-flash' or req.get('temperature')!=0 or req.get('extra_body',{}).get('thinking',{}).get('type')!='enabled':errors.append(dict(file=str(path),problem='model_or_thinking_drift'))
            if not 0<req.get('max_tokens',0)<=32768:errors.append(dict(file=str(path),problem='output_budget_drift'))
        req=input_cache[path]
        if digest([r['job'],req])!=r['job_id']:errors.append(dict(file=str(ledger),problem='job_identity_mismatch'))
        if r['event']=='result':
            responses+=1;models[r['response']['model']]+=1
            if r['job_id'] in seen:errors.append(dict(file=str(ledger),problem='duplicate_success_for_same_job'))
            seen.add(r['job_id'])
    unresolved.extend(dict(ledger=str(ledger),job=r['job'],attempt=r['attempt']) for k,r in intentions.items() if k not in finished)
for model in models:
    if model.casefold()!='deepseek-v4-flash-0731':errors.append(dict(problem='unexpected_returned_model',model=model))
if len(unresolved)!=2 or any('dev_v1/api/' not in r['ledger'] for r in unresolved):
    errors.append(dict(problem='unexpected_unfinished_request_intents',count=len(unresolved)))
for path in sorted((base/'dev_v2').glob('case*/trajectory.json')):
    tr=json.loads(path.read_text());previous=''
    for event in tr['events']:
        w=event['write']
        wrapped='<memory_context>\n'+(previous or 'None')+'\n</memory_context>\nUser: '+event['query']
        if w['before']!=previous or hashlib.sha256(wrapped.encode()).hexdigest()!=event['read_memory_sha256']:errors.append(dict(file=str(path),problem='memory_read_write_chain_mismatch',session=event['session']))
        if event['memory_entry']!=w['appended'] or not w['retained_all']:errors.append(dict(file=str(path),problem='memory_write_or_retention_failure',session=event['session']))
        previous=w['after']
    if previous!=tr['final_memory']:errors.append(dict(file=str(path),problem='final_memory_mismatch'))
for path in sorted((base/'audit_dev').glob('case*/authorized_source.json')):
    r=json.loads(path.read_text())
    if set(r['actual_docids'])&set(r['denied_docids']):errors.append(dict(file=str(path),problem='denied_document_leak'))
    if r['same_origin_as_denied_docids']:errors.append(dict(file=str(path),problem='same_origin_replacement'))
keep=preservation('/tmp/hm3-discovery-continuation-start.json')
if keep['changed']:errors.append(dict(problem='preexisting_work_changed',files=keep['changed']))
initial=json.loads(Path('/tmp/hm3-discovery-continuation-start.json').read_text())
files=subprocess.check_output(['git','ls-files','--modified','--others','--exclude-standard'],text=True).splitlines()
new=[Path(p) for p in files if p not in initial and Path(p).is_file()]
keys=[s.strip().encode() for s in Path('api/api.txt').read_text().splitlines() if s.strip() and not s.startswith('#')]
matches=[];manifest=[]
for path in sorted(new):
    raw=path.read_bytes()
    if any(k in raw for k in keys):matches.append(str(path))
    manifest.append(dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
if matches:errors.append(dict(problem='credential_match',files=matches))
result=dict(responses=responses,attempts=attempts,unique_recorded_api_inputs=len(input_cache),returned_models=dict(models),unresolved_intents=unresolved,
            required_result_rows=completeness,preservation=keep,new_files_scanned=len(new),credential_match_files=matches,errors=errors,
            note='The two abandoned v1 intents can have unknown charges; all frozen required evaluations must be complete separately.')
save(base/'verification.json',result);save(base/'file_manifest.json',manifest)
print(json.dumps(result,indent=2))
if errors:raise SystemExit(1)
