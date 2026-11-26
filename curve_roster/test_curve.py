import unittest
import numpy as np
import run_study as s

class CurveRosterTests(unittest.TestCase):
    def test_complete_feasible_grid(self):
        pairs=s.candidate_pairs()
        self.assertEqual(len(set(pairs)),190)
        self.assertEqual(sum(b==a+3 for a,b in pairs),19)
        self.assertIn((10,18),pairs)
        for a,b in pairs:
            self.assertEqual(s.windows(a,b).scheduled_per_day,360)
            self.assertEqual(sum(u-l for l,u in s.windows(a,b).windows),360)

    def test_profiles_by_day_not_pooled(self):
        # First two bins both have full exposure. Their ratio must match that day alone.
        self.assertAlmostEqual(s.profile(0)[0]/s.profile(0)[1],3963/2217)
        self.assertAlmostEqual(s.profile(1)[0]/s.profile(1)[1],3732/2003)
        self.assertAlmostEqual(s.profile(1)[23]/s.profile(1)[0],(4856/3592)/(3732/3600))
        for day in (0,1):self.assertAlmostEqual(s.profile(day).sum(),540)

    def test_gate_and_equal_class_fallback(self):
        def v(a,h,l,hi):return {"a":a,"b":20,"H_late_pct":h,"L_long_pct":l,
            "equal_class_score_pct":(h+l)/2,"L_long_pct_ci_high":hi}
        self.assertEqual(s.choose([v(3,2,4.9,5.1),v(1,6,4,4.9)])["a"],1)
        self.assertEqual(s.choose([v(3,2,9,11),v(1,6,6,8)])["a"],3)

    def test_same_alerts_and_cost(self):
        rows=s.replicate((0,77,s.profile(0),[(10,18,"DYNAMIC"),(11,16,"DYNAMIC")]))
        self.assertEqual((rows[0]["H_n"],rows[0]["L_n"]),(rows[1]["H_n"],rows[1]["L_n"]))
        for r in rows:
            self.assertAlmostEqual(r["H_late_pct"],100*r["H_late_n"]/r["H_n"])
            self.assertAlmostEqual(r["L_long_pct"],100*r["L_long_n"]/r["L_n"])
            self.assertGreaterEqual(r["paid_extra_h_day"],6)
            self.assertLess(r["paid_extra_h_day"],7)

if __name__=="__main__":unittest.main()
