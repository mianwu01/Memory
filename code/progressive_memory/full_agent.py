"""Separate native tool-capable full-agent baseline, with frozen reader scores."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

from .collect import SYSTEM,references
from .corpus import Corpus
from .discovery import trajectories
from .runtime import API,NativeClient,canonical,native_runtime,save,score
from .collect import reader_request


def run(args):
    out=Path(args.out);api=API(out/'api',max_requests=160);refs=references()
    save(out/f'config_{args.start}_{args.end}.json',dict(cases=list(range(args.start,args.end)),source=Path(__file__).read_text(),condition='Native tool-capable full agent; separate from read-only reader'))
    def worker(tr):
        path=out/f"case_{tr['case']:03d}.json"
        if path.exists():return json.loads(path.read_text())
        native=native_runtime();reads=[];corpus=Corpus(args.index,reads)
        handler=native['SearchToolHandler'](corpus,k=5,snippet_max_tokens=None)
        wrapped=reader_request(tr['final_question'],tr['entries'])['messages'][1]['content']
        req=native['build_request'](wrapped,'deepseek-v4-flash',131072,handler,system_prompt=SYSTEM,query_template='QUERY_TEMPLATE',temperature=0)
        client=NativeClient(api,f"full_agent/case{tr['case']}")
        response,combined,usage,_=native['run_conversation_with_tools'](client,req,handler,max_iterations=12)
        native_finish=response.choices[0].finish_reason
        if response.choices[0].message.tool_calls:
            response=client.create(model='deepseek-v4-flash',max_tokens=32768,messages=canonical(req['messages']+combined)+[dict(role='user',content='The search budget is now exhausted. Give your final answer using the evidence already retrieved. If it does not establish an answer, return Exact Answer: UNKNOWN. Use the requested Explanation, Exact Answer, Confidence format. Do not request more tools.')])
        ch=response.choices[0]
        row=dict(case=tr['case'],**score(ch.message.content or '',refs[tr['case']]),answer=ch.message.content or '',native_finish_reason=native_finish,
                 finish_reason=ch.finish_reason,combined=canonical(combined),source_reads=reads,usage_native_loop=usage,all_memory_retained=tr['all_memory_retained'])
        save(path,row);return row
    with ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(worker,trajectories(args.trajectories,args.start,args.end)))
    save(out/f'results_{args.start}_{args.end}.json',dict(rows=rows,correct=sum(r['correct'] for r in rows),total=len(rows)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--trajectories',required=True);p.add_argument('--out',required=True);p.add_argument('--index',required=True);p.add_argument('--start',type=int,default=0);p.add_argument('--end',type=int,default=10);run(p.parse_args())
