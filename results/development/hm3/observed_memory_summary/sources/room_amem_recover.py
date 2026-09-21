"""Reconstruct infrastructure-failed native stores using exact response replay."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import time

from . import room_memsys
from . import continuation_memsys as native
from .structure_alignment import digest


def signature(row):
    return digest({k:row.get(k) for k in ['model','messages','response_format','temperature','max_tokens']})


def main(args):
    cache={}
    original=Path('results/development/hm3/room_native/amem')/args.case/'memory_calls.jsonl'
    paths=[original]+list(Path('results/development/hm3/room_native_http_probe').glob(f'{args.case}-*.json'))
    for p in paths:
        rows=[json.loads(s) for s in p.read_text().splitlines()] if p.suffix=='.jsonl' else [json.loads(p.read_text())]
        for r in rows:
            if r['event']=='result':cache.setdefault(signature(r),(r,str(p)))
    class RecoverMeter(native.NativeMeter):
        def install(self):
            import openai
            from openai.types.chat import ChatCompletion
            parent=openai.OpenAI;meter=self
            class Metered(parent):
                def __init__(self,*a,**kw):
                    kw.update(timeout=300,max_retries=0);super().__init__(*a,**kw)
                    original_call=self.chat.completions.create
                    def measured(*a,**kw):
                        kw['max_tokens']=16384;kw['extra_body']={'thinking':{'type':'disabled'}}
                        key=signature(kw)
                        if key in cache:
                            r,where=cache[key]
                            reused={**r,'reused_from':where,'reuse_note':'Exact model/messages/schema/temperature/budget; disabled thinking'}
                            with (meter.directory/'memory_calls.jsonl').open('a') as f:f.write(json.dumps(reused)+'\n')
                            return ChatCompletion(id='replay-'+key,object='chat.completion',created=int(time.time()),
                                model=r['returned_model'],choices=r['choices'],usage=r['usage'])
                        for attempt in range(3):
                            if meter.calls>=96:raise RuntimeError('Recovery request ceiling')
                            meter.calls+=1;start=time.monotonic()
                            row={k:kw.get(k) for k in ['model','messages','response_format','temperature','max_tokens','extra_body']}
                            row.update(call=meter.calls,attempt=attempt,request_signature=key)
                            try:
                                response=original_call(*a,**kw)
                                row.update(event='result',returned_model=response.model,
                                    choices=[c.model_dump() for c in response.choices],usage=response.usage.model_dump() if response.usage else None)
                                if not response.usage or any(c.finish_reason=='length' for c in response.choices):meter.failed=True
                            except Exception as exc:
                                status=getattr(exc,'status_code',None)
                                retry=status in (400,408,429) or (isinstance(status,int) and status>=500) or type(exc).__name__ in ('APIConnectionError','APITimeoutError')
                                row.update(event='infrastructure_failure',status=status,error_type=type(exc).__name__,retryable=retry)
                            row['seconds']=time.monotonic()-start
                            with (meter.directory/'memory_calls.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
                            if row['event']=='result':return response
                            if not retry:break
                            time.sleep(2**attempt)
                        meter.failed=True
                        raise RuntimeError('Native recovery API failure; sanitized ledger retained')
                    self.chat.completions.create=measured
            openai.OpenAI=Metered
            return parent
    native.NativeMeter=RecoverMeter
    room_memsys.run(args)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case',required=True)
    p.add_argument('--system',default='amem')
    p.add_argument('--source',default='../Memory')
    p.add_argument('--repo',default='.tmp/continuation_deps/benchmarks/AgenticMemory-paper')
    p.add_argument('--actor',default='results/development/hm3/room_actor_v1')
    p.add_argument('--out',default='results/development/hm3/room_native_recovery')
    p.add_argument('--key-file',default='api/api.txt')
    main(p.parse_args())
