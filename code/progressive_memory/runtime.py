"""Pinned native functions plus a logged Flash-thinking transport adapter."""
from __future__ import annotations
import ast
import copy
import hashlib
import json
from pathlib import Path
import re
import threading
import time
import types
import unicodedata

import openai
import tiktoken

ROOT=Path(__file__).resolve().parents[2]
UPSTREAM=ROOT.parent/'Memory/benchmarks/MemoryArena'
MODEL='deepseek-v4-flash'
ENDPOINT='https://www.autodl.art/api/v1'


def save(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    value=json.dumps(obj,indent=2,ensure_ascii=False)+'\n'
    if path.exists():
        if path.read_text()!=value:raise ValueError('Frozen artifact mismatch: '+path.name)
    else:path.write_text(value)


def canonical(obj):
    if hasattr(obj,'model_dump'):return canonical(obj.model_dump(exclude_none=True))
    if isinstance(obj,dict):return {k:canonical(v) for k,v in obj.items() if v is not None}
    if isinstance(obj,(tuple,list)):return [canonical(v) for v in obj]
    return obj


def digest(obj):return hashlib.sha256(json.dumps(canonical(obj),sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def extract(text):
    m=re.findall(r'(?im)^\s*\*{0,2}Exact Answer\*{0,2}\s*:\*{0,2}\s*([^\n]+)',text)
    return m[-1].strip() if m else None


def normalize(text):
    text=unicodedata.normalize('NFKC',text or '').casefold()
    text=re.sub(r'\[\d+\]','',text).replace('**','').replace('`','')
    return ' '.join(text.strip(' \n\t.,;:!?\"\'').split())


def score(text,answer):return dict(extracted=extract(text),correct=bool(extract(text) is not None and normalize(extract(text))==normalize(answer)))


def native_definitions(path,names,namespace):
    source=Path(path).read_text();tree=ast.parse(source)
    nodes=[n for n in tree.body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in names]
    assert {n.name for n in nodes}==set(names)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),namespace)
    return hashlib.sha256(source.encode()).hexdigest()


def native_runtime():
    namespace=dict(copy=copy,json=json,openai=openai,list_of_requests=[],list_of_responses=[])
    promptpath=UPSTREAM/'env/env_systems/web_search_env/search_agent/prompts.py'
    exec(compile(promptpath.read_text(),str(promptpath),'exec'),namespace)
    agentpath=UPSTREAM/'env/env_systems/web_search_env/search_agent/openai_client.py'
    native_definitions(agentpath,['SearchToolHandler','build_request','run_conversation_with_tools'],namespace)
    return namespace


class Memory:
    def __init__(self):
        # Native timestamps are assigned logical write times for byte-exact resume.
        clock=types.SimpleNamespace(strftime=lambda fmt:'2026-09-22 00:00:00')
        ns=dict(time=clock,tiktoken=tiktoken,Optional=__import__('typing').Optional)
        native_definitions(UPSTREAM/'memory/memory_systems/long_context.py',['LongContextMemorySystem'],ns)
        self.clock=clock;self.store=ns['LongContextMemorySystem'](max_tokens=500000)
        self.entries=[]

    def add(self,text,session):
        self.clock.strftime=lambda fmt:f'2026-09-22 00:{session:02d}:00'
        before=self.store.context;self.store.add_chunk(text);self.entries.append(text)
        return dict(session=session,write_wall_time=time.time(),before=before,after=self.store.context,
                    appended=text,retained_all=all(e in self.store.context for e in self.entries))

    def wrap(self,query):return self.store.wrap_user_prompt(query)


class API:
    def __init__(self,directory,key_file='api/api.txt',max_requests=1200):
        self.out=Path(directory);self.out.mkdir(parents=True,exist_ok=True)
        keys=[s.strip() for s in Path(key_file).read_text().splitlines() if s.strip() and not s.strip().startswith('#')]
        self.clients=[openai.OpenAI(api_key=k,base_url=ENDPOINT,timeout=600,max_retries=0) for k in keys]
        self.lock=threading.Lock();self.limit=max_requests
        self.requests=self.out/'requests.jsonl';self.ledger=self.out/'ledger.jsonl'
        self.rows=[json.loads(s) for s in self.ledger.read_text().splitlines()] if self.ledger.exists() else []
        self.done={r['job_id']:r for r in self.rows if r['event']=='result'}
        self.attempts=[json.loads(s) for s in self.requests.read_text().splitlines()] if self.requests.exists() else []
        self.started=len(self.attempts)

    def append(self,path,row):
        with path.open('a') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush()

    def call(self,job,request):
        req=canonical(request);req['model']=MODEL;req['temperature']=0
        req['max_tokens']=min(32768,req.pop('max_completion_tokens',req.get('max_tokens',32768)))
        req.pop('reasoning',None);req['extra_body']={'thinking':{'type':'enabled'}}
        ident=digest([job,req]);sha=digest(req)
        if ident in self.done:return openai.types.chat.ChatCompletion.model_validate(self.done[ident]['response'])
        if any(r['job_id']==ident and r['event']=='infrastructure_failure' and not r['retryable'] for r in self.rows):
            raise RuntimeError('Previously recorded non-retryable transport failure')
        previous=[r for r in self.attempts if r['job_id']==ident]
        for attempt in range(len(previous),3):
            with self.lock:
                if self.started>=self.limit:raise RuntimeError('Recorded API request cap reached')
                self.started+=1;index=self.started
                save(self.out/'inputs'/f'{sha}.json',req)
                intent=dict(job=job,job_id=ident,prompt_sha256=sha,attempt=attempt,started_at=time.time())
                self.append(self.requests,intent);self.attempts.append(intent)
            start=time.monotonic()
            try:
                response=self.clients[index%len(self.clients)].chat.completions.create(**req)
            except Exception as e:
                status=getattr(e,'status_code',None)
                retry=type(e).__name__ in ('APITimeoutError','APIConnectionError') or status in (408,429) or (isinstance(status,int) and status>=500)
                row={**intent,'event':'infrastructure_failure','error_type':type(e).__name__,'status':status,'retryable':retry,'seconds':time.monotonic()-start}
                with self.lock:self.append(self.ledger,row)
                if not retry:raise RuntimeError(f'{type(e).__name__}; status={status}') from None
                time.sleep(2**attempt);continue
            row={**intent,'event':'result','response':response.model_dump(),'seconds':time.monotonic()-start}
            with self.lock:
                self.append(self.ledger,row);self.done[ident]=row
                print(json.dumps(dict(job=job,event='result',finish_reason=response.choices[0].finish_reason,usage=response.usage.model_dump() if response.usage else None)),flush=True)
            return response
        raise RuntimeError('Transport attempts exhausted')


class NativeClient:
    def __init__(self,api,namespace):
        self.api=api;self.namespace=namespace;self.iteration=0;self.reasoning={}
        self.chat=types.SimpleNamespace(completions=self)

    def create(self,**request):
        request=canonical(request)
        for msg in request['messages']:
            if msg['role']=='assistant' and msg.get('tool_calls'):
                tc=msg['tool_calls'][0]['id']
                if tc in self.reasoning:msg['reasoning_content']=self.reasoning[tc]
        response=self.api.call(f'{self.namespace}/turn{self.iteration}',request);self.iteration+=1
        msg=response.choices[0].message
        for call in msg.tool_calls or []:self.reasoning[call.id]=getattr(msg,'reasoning_content','') or ''
        return response
