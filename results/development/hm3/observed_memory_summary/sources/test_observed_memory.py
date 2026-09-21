"""Offline regression tests for the new representation and actor bridge."""
import json
from pathlib import Path
import random
import unittest

import numpy as np

from .observed_room import bh,discover,init,selection
from .paired_actor import prepare
from .room_actor import parse
from .room_source_audit import collect,intervene,load_model
from .room_native_actor import replace_memory
from .room_closure import bm25, rotate_graph, safe_answer, sensitivity_graph
from .room_belief_diagnostic import joint_belief


class ObservedMemoryTests(unittest.TestCase):
    def test_native_replacement_changes_only_memory(self):
        original=[dict(role='system',content='fixed'),dict(role='user',content=
            'MODEL\nMEMORY RECORDS [kind,time,entity,value]\n[]\nQUESTION\nQ')]
        changed=replace_memory(original,'native output')
        self.assertEqual(changed[0],original[0])
        self.assertEqual(changed[1]['content'],'MODEL\nMEMORY RECORDS [kind,time,entity,value]\nnative output\nQUESTION\nQ')
        self.assertIn('\n[]\n',original[1]['content'])

    def test_distinct_rotations_and_train_only_sensitivity(self):
        walls=['a','b','c','d'];g={('o','room'):{'c'}}
        rotated=[rotate_graph(g,walls,i)[('o','room')] for i in [1,2,3]]
        self.assertEqual(len({tuple(sorted(x)) for x in rotated}),3)
        self.assertTrue(all('c' not in x for x in rotated))
        model={'incident':{'room':{'a','b'}},'table':{
            ('o','room',(0,0)):'left',('o','room',(1,0)):'right',
            ('o','room',(0,1)):'left'}}
        self.assertEqual(sensitivity_graph(model)[('o','room')],{'a'})

    def test_controller_does_not_accept_guess_or_ambiguous_state(self):
        self.assertIsNone(safe_answer(True,'left',['left','right']))
        self.assertIsNone(safe_answer(True,'right',['left']))
        self.assertIsNone(safe_answer(False,'left',['left']))
        self.assertEqual(safe_answer(True,'left',['left']),'left')

    def test_bm25_record_budget_and_nonmutation(self):
        records=[('sight',t,'mary' if t==3 else 'john','kitchen') for t in range(10)]
        original=list(records)
        selected=bm25(records,4)
        self.assertEqual(records,original)
        self.assertEqual(len(selected),4)
        self.assertIn(records[3],selected)
        self.assertEqual(selected,sorted(selected,key=lambda r:r[1]))

    def test_joint_phase_check_does_not_drop_unknown_transition(self):
        knowledge=dict(patterns={'w':[0,1]},rooms=['a','b'],incident_walls={'a':['w']},
                       transitions=[dict(room='a',wall_bits=[0],next_room='a')])
        answer=joint_belief([['sight',0,'mary','a']],knowledge,'mary',1)
        self.assertTrue(answer['missing_transition'])
        self.assertEqual(answer['rooms'],['a','b'])

    def test_joint_phase_check_rejects_contradictory_observations(self):
        knowledge=dict(patterns={'w':[0,1]},rooms=['a','b'],incident_walls={},transitions=[])
        answer=joint_belief([['wall',0,'w',0],['wall',0,'w',1]],knowledge,'mary',1)
        self.assertTrue(answer['inconsistent_observations'])
        self.assertEqual(answer['rooms'],[])

    def test_paired_actor_inputs_identical_between_modes(self):
        eps,jobs=prepare()
        self.assertEqual(len(jobs),72)
        self.assertEqual(len({j['job_id'] for j in jobs}),72)
        for ep in eps:
            for arm in ['full','no_history','policy_oracle']:
                subset=[j for j in jobs if j['case']==ep.id and j['arm']==arm]
                self.assertEqual(len({j['prompt_sha256'] for j in subset}),1)
        oracle=[j for j in jobs if j['arm']=='policy_oracle'][0]
        empty=[j for j in jobs if j['arm']=='no_history'][0]
        self.assertIn('DIAGNOSTIC ONLY',oracle['messages'][1]['content'])
        self.assertNotIn('DIAGNOSTIC ONLY',empty['messages'][1]['content'])

    def test_parser_requires_named_room(self):
        self.assertEqual(parse('```json\n{"room":"living"}\n```'),(True,'living'))
        self.assertEqual(parse('{"room":null}'),(True,None))
        self.assertEqual(parse('{"other":"living"}'),(False,None))

    def test_real_lag_conditioned_discovery(self):
        recs=[]
        for seed in range(4):
            rng=np.random.default_rng(seed+101)
            walls=rng.integers(0,2,(256,2))
            loc=np.r_[0,walls[:-1,0]]
            recs.append([dict(walls={'w0':int(w[0]),'w1':int(w[1])},loc={'o':str(l)}) for w,l in zip(walls,loc)])
        graph,fit=discover(recs,dict(walls=['w0','w1'],objs=['o']))
        self.assertEqual(graph[('o','0')],{'w0'})
        self.assertEqual(graph[('o','1')],{'w0'})
        self.assertEqual(fit['train_trajectories'],4)

    def test_bh_empty_and_signal(self):
        self.assertEqual(bh([]).tolist(),[])
        self.assertEqual(bh([.00001,.8,.9]).tolist(),[True,False,False])

    def test_sensor_is_separate_and_intervention_does_not_mutate_memory(self):
        checkout=Path('/tmp/observed-memory-20260922-LMbAYg/room-env')
        if not checkout.exists():self.skipTest('Pinned optional RoomEnv checkout absent')
        base,old=init(checkout,'small-01',120)
        model,graph=load_model('results/development/hm3/observed_room_small',base)
        data=collect(base,model,6100)
        records=data['snapshots'][50]['records'];before=list(records)
        source='living|kitchen|vertical'
        blocked,changed=intervene(records,source,data['patterns'])
        self.assertEqual(records,before)
        self.assertNotEqual(records,changed)
        self.assertTrue(all(not(r[0]=='wall' and r[2]==source) for r in blocked))
        fetched=[('wall',r[1],source,data['sensor'][source,r[1]]) for r in records if r[0]=='wall' and r[2]==source]
        self.assertEqual(set(blocked+fetched),set(records))
        selections={p:selection(p,records,'mary',50,8,model,graph,random.Random(1),old)
                    for p in ['learned','topology','complete','recency','ledger','random']}
        self.assertTrue(all(len(v)==8 for v in selections.values()))
        self.assertNotEqual(selections['learned'],selections['topology'])


if __name__=='__main__':unittest.main()
