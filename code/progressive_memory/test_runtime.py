import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from openai.types.chat import ChatCompletion
from .runtime import Memory, NativeClient, native_runtime, score
from .collect import reader_request

class TestRuntime(unittest.TestCase):
    def test_resume_and_subset(self):
        original=Memory();original.add('alpha',0);original.add('beta',3)
        rebuilt=Memory();rebuilt.add('alpha',0);rebuilt.add('beta',3)
        self.assertEqual(original.store.context,rebuilt.store.context)
        req=reader_request('q',['beta'],[3])
        self.assertIn('00:03:00',req['messages'][1]['content'])
        self.assertNotIn('alpha',req['messages'][1]['content'])

    def test_native_loop_reasoning_and_namespaces(self):
        def response(message,finish):
            return ChatCompletion.model_validate(dict(id='test',object='chat.completion',created=0,model='deepseek-v4-flash-0731',choices=[dict(index=0,finish_reason=finish,message=message)],usage=dict(prompt_tokens=10,completion_tokens=2,total_tokens=12)))
        responses=[response(dict(role='assistant',content='',reasoning_content='private reasoning',tool_calls=[dict(id='call1',type='function',function=dict(name='search',arguments='{"query":"example"}'))]),'tool_calls'),response(dict(role='assistant',content='Exact Answer: example'),'stop')]
        requests=[]
        def call(job,req):requests.append(req);return responses[len(requests)-1]
        corpus=SimpleNamespace(search_description=lambda k:'Search',get_document_description=lambda:'Read',search=lambda *args,**kw:[dict(docid='d1',text='example')])
        runtime=native_runtime();other=native_runtime()
        handler=runtime['SearchToolHandler'](corpus)
        req=runtime['build_request']('q','deepseek-v4-flash',100,handler)
        final,combined,usage,_=runtime['run_conversation_with_tools'](NativeClient(SimpleNamespace(call=call),'fake'),req,handler,max_iterations=3)
        self.assertEqual(final.choices[0].message.content,'Exact Answer: example')
        self.assertEqual(requests[1]['messages'][1]['reasoning_content'],'private reasoning')
        self.assertEqual(json.loads(requests[1]['messages'][2]['content'])[0]['docid'],'d1')
        self.assertEqual(len(runtime['list_of_responses']),2)
        self.assertEqual(other['list_of_responses'],[])

    def test_strict_checker(self):
        self.assertTrue(score('Exact Answer: **Paris.**','paris')['correct'])
        self.assertFalse(score('Paris','Paris')['correct'])
        self.assertFalse(score('Exact Answer: Paris or London','Paris')['correct'])

if __name__=='__main__':unittest.main()
