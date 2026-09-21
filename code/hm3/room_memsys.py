"""Native Mem0/A-Mem on exactly the RoomEnv actor's observational history."""
from __future__ import annotations
import argparse
import contextlib
import io
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from types import SimpleNamespace

from .continuation_actor import write_once
from . import continuation_memsys as native


def run(args):
    source=Path(args.source).resolve();root=Path(args.out)
    os.environ.update(CUDA_VISIBLE_DEVICES='',TOKENIZERS_PARALLELISM='false',MEM0_TELEMETRY='false',
        ANONYMIZED_TELEMETRY='false',OPENAI_BASE_URL=native.ENDPOINT,
        NLTK_DATA=str(source/'.tmp/nltk_data'),FASTEMBED_CACHE_PATH=str(source/'.tmp/fastembed'))
    key=next(s.strip() for s in Path(args.key_file).read_text().splitlines() if s.strip() and not s.strip().startswith('#'))
    os.environ['OPENAI_API_KEY']=key
    repo_name,pinned=native.COMMITS[args.system]
    repo=Path(args.repo).resolve() if args.repo else source/'benchmarks'/repo_name
    actual=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    dirty=subprocess.check_output(['git','-C',str(repo),'status','--porcelain'],text=True).strip()
    if actual!=pinned or dirty:raise RuntimeError('Pinned author checkout mismatch')
    sys.path.insert(0,str(repo))
    native.MODEL='deepseek-v4-flash'
    native.CONFIG={**native.CONFIG,'extra_body':{'thinking':{'type':'disabled'}}}
    # Adapter grouping is explicit: input is already a list of five-step batches.
    # Do not label mere observations as HM3 interventions to trigger its splitter.
    native.segments=lambda groups:groups
    if args.system=='amem':
        import memory_layer
        memory_layer.re=re
    actor_root=Path(args.actor)
    profiles=json.loads((actor_root/'case_profiles.json').read_text())
    for profile in profiles:
        case=profile['case'];directory=root/args.system/case
        if args.case and case!=args.case:continue
        directory.mkdir(parents=True,exist_ok=True)
        if (directory/'status.json').exists():
            print((directory/'status.json').read_text(),flush=True);continue
        # Reconstruct original input from the prepared actor, without world truth.
        manifest=json.loads((actor_root/'manifest.json').read_text())
        entry=next(j for j in manifest if j['case']==case and j['arm']=='full')
        messages=json.loads((actor_root/'inputs'/f"{entry['prompt_sha256']}.json").read_text())
        raw=messages[1]['content'].split('MEMORY RECORDS [kind,time,entity,value]\n',1)[1].split('\nQUESTION\n',1)[0]
        records=json.loads(raw)
        groups=[[r for r in records if start<=r[1]<start+5] for start in range(0,51,5)]
        groups=[g for g in groups if g]
        ep=SimpleNamespace(id=case,H=groups,query='Where is mary at environment time 50?',I={'object':'mary','time':50})
        store=(Path('.tmp')/'room_native_stores'/root.name/args.system/case).resolve()
        os.environ['MEM0_DIR']=str(store/'mem0_home')
        write_once(directory/'protocol.json',dict(system=args.system,case=case,commit=actual,
            model=native.MODEL,thinking='disabled',memory_native_k=8,grouping='5 actual environment steps',
            true_world_state_supplied=False,discovered_graph_supplied=False,
            document='docs/observed-memory-next-protocol-2026-09-22.md'))
        meter=native.NativeMeter(directory);start=time.monotonic();status=dict(system=args.system,case=case)
        capture=io.StringIO();errors=[]
        class Capture(logging.Handler):
            def emit(self,record):
                if record.levelno>=logging.ERROR:errors.append(record.name)
        handler=Capture();logging.getLogger().addHandler(handler)
        try:
            store.mkdir(parents=True,exist_ok=False)
            import openai
            parent=meter.install()
            try:
                with contextlib.redirect_stdout(capture),contextlib.redirect_stderr(capture):
                    result=native.build_memory(args.system,ep,store,source,directory)
            finally:
                openai.OpenAI=parent
            markers=[s for s in ['error analyzing','error processing api','storing without evolution'] if s in capture.getvalue().lower()]
            write_once(directory/'memory_output.json',result)
            if meter.failed or errors or markers:
                status.update(status='invalid_execution',api_invalid=meter.failed,loggers=errors,markers=markers)
            else:status.update(status='completed',characters=len(result['text']))
        except Exception as exc:
            import traceback
            status.update(status='invalid_execution',error_type=type(exc).__name__,
                traceback=[dict(file=Path(x.filename).name,line=x.lineno,function=x.name) for x in traceback.extract_tb(exc.__traceback__)])
        finally:logging.getLogger().removeHandler(handler)
        status.update(memory_calls=meter.calls,seconds=time.monotonic()-start)
        write_once(directory/'status.json',status)
        print(json.dumps(status),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--system',choices=['mem0','amem'],required=True)
    p.add_argument('--source',default='../Memory')
    p.add_argument('--repo',help='Optional clean pinned checkout; model caches still use --source')
    p.add_argument('--case',help='Run one case in an isolated process')
    p.add_argument('--actor',default='results/development/hm3/room_actor_v1')
    p.add_argument('--out',default='results/development/hm3/room_native')
    p.add_argument('--key-file',default='api/api.txt')
    run(p.parse_args())
