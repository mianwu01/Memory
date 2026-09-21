import unittest
import numpy as np
from .audit import modified_conditions
from .selection import ancestors,trim_entries,ENC
from .discovery import fit_panel

class TestControls(unittest.TestCase):
    def test_graph_direction_and_transitive_ancestry(self):
        graph=[[False,True,False],[False,False,True],[False,False,False]]
        self.assertEqual(ancestors(graph,2),{0,1,2})
        self.assertEqual(ancestors(graph,0),{0})

    def test_budget_and_short_record_residual(self):
        entries=['short','a detailed observation. '*1000]
        selected,alloc=trim_entries(entries,[0,1],budget=101,per_entry=8192)
        self.assertEqual(sum(alloc),101)
        self.assertEqual(selected[0],'short')
        self.assertLessEqual(sum(len(ENC.encode(s)) for s in selected),101)

    def test_actual_interventions_and_redundancy_disclosure(self):
        tr=dict(case=4,final_question='Who won?',entries=['Ada won the award.','Other evidence names Ada.'],events=[dict(source_reads=[dict(tool='search',results=[dict(docid='42')])]),dict(source_reads=[])])
        plan=dict(methods=dict(discovered=dict(indices=[0])),bm25=[2,1])
        r=modified_conditions(tr,plan,dict(extracted='Ada'))
        self.assertEqual(r['replacements'],1)
        self.assertEqual(r['answer_occurrences_outside_target'],1)
        self.assertEqual(r['denied_docids'],['42'])
        self.assertNotIn('Ada won',r['conditions']['blocked']['messages'][1]['content'])
        self.assertIn('Counterfactual Entity 4 won',r['conditions']['changed']['messages'][1]['content'])
        self.assertIn('Ada won',r['conditions']['neutral']['messages'][1]['content'])
        self.assertEqual(r['conditions']['blocked'],r['conditions']['complete_blocked'])
        self.assertEqual(r['conservative_source_block_remaining'],[])
        self.assertEqual(r['conditions']['source_blocked'],r['conditions']['no_evidence'])

    def test_rewired_controls_are_actually_different(self):
        from .rewired_controls import deranged_graphs
        graphs=list(deranged_graphs().values())
        self.assertEqual(len({str(g) for g in graphs}),3)
        for graph in graphs:
            a=np.array(graph)
            self.assertFalse(np.diag(a).any())
            self.assertTrue((a.sum(axis=0)==1).all())
            self.assertTrue((a.sum(axis=1)==1).all())

    def test_authorized_evidence_does_not_promote_writer_guesses(self):
        from .evidence_only import evidence_entry
        source=dict(combined=[dict(role='assistant',content='UNSUPPORTED_GUESS: NYU'),
                              dict(role='tool',name='get_document',content='The actual document compares NYU with Amherst College.')])
        entry=evidence_entry(source,'Which college?')
        self.assertNotIn('UNSUPPORTED_GUESS',entry)
        self.assertIn('The actual document compares NYU with Amherst College.',entry)

    def test_native_multiple_trajectory_pcmci_integration(self):
        rng=np.random.default_rng(7);panel=[]
        for _ in range(15):
            x=rng.normal(size=(30,4));x[1:,1]=1.5*x[:-1,0]+.2*x[1:,1];panel.append(x)
        fit=fit_panel(panel)
        self.assertTrue(fit['adjacency'][0][1])
        self.assertFalse(fit['adjacency'][1][0])

if __name__=='__main__':unittest.main()
