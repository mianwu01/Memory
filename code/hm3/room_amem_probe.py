"""One recorded diagnostic retry for each native A-Mem HTTP failure."""
import json
from pathlib import Path
import time

from .continuation_actor import write_once
from .structure_alignment import digest


def main():
    import openai
    keys=[s.strip() for s in Path('api/api.txt').read_text().splitlines() if s.strip() and not s.strip().startswith('#')]
    client=openai.OpenAI(api_key=keys[0],base_url='https://www.autodl.art/api/v1',timeout=300,max_retries=0)
    out=Path('results/development/hm3/room_native_http_probe');out.mkdir(parents=True,exist_ok=True)
    for p in sorted(Path('results/development/hm3/room_native/amem').glob('*/memory_calls.jsonl')):
        for line in p.read_text().splitlines():
            old=json.loads(line)
            if old['event']=='result':continue
            dest=out/f'{p.parent.name}-{old["call"]}.json'
            if dest.exists():continue
            req={k:old[k] for k in ['model','messages','response_format','temperature','max_tokens']}
            req['extra_body']={'thinking':{'type':'disabled'}}
            row=dict(**{k:old[k] for k in ['model','messages','response_format','temperature','max_tokens']},
                     source_case=p.parent.name,source_failure_call=old['call'],request_hash=digest(req),
                     extra_body=req['extra_body'],diagnostic_retry=True)
            started=time.monotonic()
            try:
                r=client.chat.completions.create(**req)
                row.update(event='result',returned_model=r.model,choices=[c.model_dump() for c in r.choices],
                           usage=r.usage.model_dump() if r.usage else None)
            except Exception as exc:
                body=json.dumps(getattr(exc,'body',None),ensure_ascii=False)
                for key in keys:body=body.replace(key,'[REDACTED]')
                row.update(event='infrastructure_failure',status=getattr(exc,'status_code',None),
                           error_type=type(exc).__name__,sanitized_error_body=body[:2000])
            row['seconds']=time.monotonic()-started
            write_once(dest,row)
            print(json.dumps({k:row.get(k) for k in ['source_case','event','status','sanitized_error_body','seconds']}),flush=True)


if __name__=='__main__':main()
