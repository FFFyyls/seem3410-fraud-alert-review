"""Boundary and decision checks; run with python -B -m unittest discover -s this_folder."""
import unittest,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
import experiment as e
from study import remap_inputs

class TestPostedSchedule(unittest.TestCase):
    def test_all_windows_have_same_preposted_hours_and_are_separate(self):
        self.assertEqual(len(set(e.GRID)),25)
        for a,b in e.GRID:
            fixed=e.DailyWindows([(600+a,780+a),(1080+b,1260+b)])
            self.assertEqual(fixed.scheduled_per_day,360)
    def test_identity_and_existing_time_transform(self):
        x=e.generate_inputs('B',1811,3,4)
        for pair in [(0,0),(60,60),(-59.5,47)]:
            a,b=pair
            y=e.change_timing(x,np.tile(pair,(4,1)))
            ref=remap_inputs(x,[0,600+a,780+a,1080+b,1260+b,1440],e.BASE_RATES)
            np.testing.assert_allclose(y.arrival,ref.arrival,rtol=0,atol=1e-10)
            np.testing.assert_array_equal(y.risk,x.risk);np.testing.assert_array_equal(y.service,x.service)
            np.testing.assert_array_equal(y.arrival//1440,x.arrival//1440)
    def test_independent_peak_stream_extends_and_differs(self):
        a=e.shift_draws(100,1,35)
        np.testing.assert_array_equal(e.shift_draws(100,1,42)[:35],a)
        self.assertFalse(np.array_equal(a[:,0],a[:,1]))
        self.assertFalse(np.array_equal(a,e.shift_draws(100,2,35)))
        self.assertFalse(np.array_equal(a,e.shift_draws(101,1,35)))
    def test_select_h_only_after_low_risk_screen(self):
        def row(l,h,up,o=0):
            return dict(L_long_pct=l,H_late_pct=h,L_long_pct_hi=up,lunch_offset=o,evening_offset=o)
        infeasible=row(4.85,1,5.22);eligible=row(4.1,4,4.5);better_h=row(4.2,3,4.6);flat=row(4.2,3,4.6,30)
        self.assertEqual(e.choose([infeasible,eligible,better_h,flat]),(better_h,3))
        other=row(4.95,.9,5.01)
        self.assertEqual(e.choose([infeasible,other]),(infeasible,0))

if __name__=='__main__': unittest.main()
