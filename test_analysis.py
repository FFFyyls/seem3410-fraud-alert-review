"""Unit tests of the reporting layer. Run: python -m unittest test_analysis -v"""
import unittest
from types import SimpleNamespace
import numpy as np
from analysis import summarize, paired, mean_ci, decide_warmup, decide_replications, guardrail

class AnalysisTests(unittest.TestCase):
    def test_sla_equality_is_timely_and_measured_by_completion(self):
        r = SimpleNamespace(
            arrival=np.array([0,0,0,1,4.]), start=np.array([15,16,0,61,65.]),
            finish=np.array([30,31,60,121,125.]), risk=np.array([0,0,1,2,2]),
            mean_queue=2.5, utilization=.7, max_queue=9, backlog_at_end=4, unfinished_at_end=5)
        row = summarize(r)
        self.assertEqual(row['H_completion_late'],.5)
        self.assertEqual(row['H_start_by15'],.5)
        self.assertEqual(row['M_completion_late'],0)
        self.assertEqual(row['L_wait_gt60'],.5)
        self.assertEqual(row['L_completion_late'],.5)
        self.assertAlmostEqual(row['L_p95_wait_min'],60.95)
        self.assertEqual(row['L_n'],2)
    def test_paired_matches_replication_ids_and_exports_pp(self):
        base=[dict(rep=i,H_completion_late=x) for i,x in [(2,.4),(4,.5),(1,.3)]]
        alt=[dict(rep=i,H_completion_late=x) for i,x in [(1,.28),(2,.38),(4,.48)]]
        p=paired(alt,base,'H_completion_late')
        self.assertAlmostEqual(p['estimate'],-2.0)
        self.assertEqual(p['unit'],'pp')
        self.assertAlmostEqual(p['halfwidth'],0)
        with self.assertRaises(ValueError): paired(alt,base[:-1],'H_completion_late')
    def test_empty_class_is_na_not_instant_success(self):
        from analysis import class_metrics
        x=class_metrics(np.array([0]),np.array([1.]),np.array([23.]))
        self.assertEqual(x['L_n'],0)
        self.assertTrue(np.isnan(x['L_wait_gt60']))
        self.assertTrue(np.isnan(x['M_completion_ontime']))
        self.assertEqual(mean_ci([np.nan,1.,2.,3.])['n_reps'],3)
    def test_t_interval_uses_replications(self):
        a=mean_ci([1,2,3]); self.assertAlmostEqual(a['halfwidth'],4.3026527297/3**.5, places=9)
    def test_pilot_freeze(self):
        self.assertEqual(decide_warmup([dict(metric='H_completion_late', estimate=1.1,ci_low=-.2,ci_high=2.4)]),7)
        self.assertEqual(decide_warmup([dict(metric='L_p95_wait_min',estimate=-2.1,ci_low=-3.1,ci_high=-1.1)]),14)
        self.assertEqual(decide_replications([41.1]),50)
        self.assertEqual(decide_replications([101]),100)
        self.assertEqual(guardrail(5.0,8.0),'uncertain')
        self.assertEqual(guardrail(4.0,5.0),'meets')
        self.assertEqual(guardrail(5.1,7.0),'exceeds')

if __name__=='__main__': unittest.main()

