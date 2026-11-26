"""New contracts: matched demand timing, proxy shape and fixed arrival cohorts."""
import importlib.util
from pathlib import Path
import unittest
import numpy as np
from engine import Inputs, generate_inputs


class StudyTests(unittest.TestCase):
    def module(self):
        path=Path(__file__).with_name('study.py')
        self.assertTrue(path.is_file(), 'study.py implementation is missing')
        spec=importlib.util.spec_from_file_location('study',path)
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        return m

    def test_identity_profile_retains_every_input(self):
        m=self.module();x=generate_inputs('B',34101600,0,3)
        y=m.remap_inputs(x,[0,600,780,1080,1260,1440],[18,36,18,36,18])
        np.testing.assert_allclose(y.arrival,x.arrival,atol=1e-10)
        np.testing.assert_equal(y.risk,x.risk);np.testing.assert_equal(y.service,x.service)

    def test_delayed_peaks_map_cumulative_intensity_not_blind_clock_shift(self):
        m=self.module()
        x=Inputs(np.array([0,600,630,780,1080,1110,1260,1430,1440.]),np.zeros(9),np.ones(9),2880)
        y=m.remap_inputs(x,[0,660,840,1140,1320,1440],[18,36,18,36,18])
        np.testing.assert_allclose(y.arrival,[0,600,660,810,1080,1140,1290,1430,1440])
        np.testing.assert_equal(y.arrival//1440,x.arrival//1440)

    def test_profile_zero_intervals_and_wrong_total(self):
        m=self.module();x=Inputs([0,1,1000],[0,1,2],[1,2,3],1440)
        y=m.remap_inputs(x,[0,720,1440],[0,45])
        self.assertTrue(np.all(y.arrival>=720))
        with self.assertRaises(ValueError):m.remap_inputs(x,[0,720,1440],[18,18])

    def test_proxy_uses_exposure_and_preserves_assumed_daily_total(self):
        m=self.module()
        rows=[dict(day=0,hour=h,count=10,exposure_seconds=3600) for h in range(24)]
        rows.append(dict(day=1,hour=0,count=5,exposure_seconds=1800))
        rates=m.proxy_hourly_rates(rows,0)
        np.testing.assert_allclose(rates,np.full(24,22.5))
        rows[0]['count']=20
        a=m.proxy_hourly_rates(rows,0);b=m.proxy_hourly_rates(rows,12)
        self.assertAlmostEqual(float(a.sum()),540)
        np.testing.assert_equal(b,np.roll(a,12))

    def test_fixed_windows_are_arrival_based_and_half_open(self):
        m=self.module()
        arr=np.array([779,780,839,840,1259,1260,1319,1320.]);risk=np.full(8,2)
        waits=np.array([100,61,60,100,100,61,61,100.])
        met=m.arrival_metrics(risk,arr,waits,waits+4)
        self.assertEqual(met['L_wait_gt60_arrive_13_14'],.5)
        self.assertEqual(met['L_wait_gt60_arrive_21_22'],1)
        self.assertEqual(met['L_arrive_13_14_n'],2)

    def test_gates_keep_new_diagnostics_separate_and_use_intervals(self):
        m=self.module()
        row=m.decision_gates(4.9,5.1,4.8,-2.1)
        self.assertTrue(row['aggregate_pass']);self.assertFalse(row['fixed_windows_pass'])
        self.assertTrue(row['H_benefit_pass']);self.assertFalse(row['protected_candidate'])
        self.assertTrue(m.decision_gates(5,5,5,-2)['protected_candidate'])


if __name__=='__main__':unittest.main()
