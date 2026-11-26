import unittest
import numpy as np
import run_budget as b
from engine import generate_inputs,simulate

class BudgetDesignTests(unittest.TestCase):
    def test_candidates(self):
        n=0
        for budget in range(25):
            plans=b.space(budget);n+=len(plans)
            self.assertEqual(len(set(plans)),len(plans))
            for w in plans:
                self.assertEqual(b.parse(b.key(w)),w)
                self.assertEqual(sum(z-a for a,z in w),budget)
                self.assertTrue(all(0<=a<z<=24 for a,z in w))
                if len(w)==2:
                    (a,z),(x,y)=w;self.assertLess(z,x)
                    self.assertLessEqual(abs(z-a-(y-x)),1)
        self.assertEqual(n,3271)
        self.assertEqual(len(b.space(6)),190)
        self.assertEqual(b.space(0),[()])
        self.assertEqual(b.space(24),[((0,24),)])
        self.assertIn(((1,2),(4,6)),b.space(3))
        self.assertIn(((1,3),(4,5)),b.space(3))

    def test_six_hour_training_policy_preserved(self):
        v=b.choose(b.import_six())
        self.assertEqual(v["window"],"11-14/16-19")
        self.assertAlmostEqual(v["H_late_pct"],35.4731156437189)

    def test_endpoints_agree_with_fixed_engine(self):
        rates=b.profile(0);seed=33;rep=0;plans=[((),"DYNAMIC"),(((0,24),),"DYNAMIC")]
        rr=b.replay((rep,seed,rates,plans))
        x=b.remap_inputs(generate_inputs("B",seed,rep,35),np.arange(0,1441,60),rates)
        for t,c in zip(rr,(3,4)):
            r=dict(zip(b.FIELDS,t))
            y=simulate(x,"DYNAMIC",c,14*1440,28*1440,20.)
            self.assertEqual(r["H_late_n"],int(np.count_nonzero((y.risk==0)&(y.finish-y.arrival>30))))
            self.assertEqual(r["L_long_n"],int(np.count_nonzero((y.risk==2)&(y.start-y.arrival>60))))
            self.assertEqual(r["paid_extra_h_day"],float((c-3)*24))

    def test_boundary_need_not_be_monotonic(self):
        tab=[dict(budget=i,L_point_pass=i in (1,3),L_sim_pass=i==3,joint_daily_pass=i==3) for i in range(4)]
        self.assertEqual(b.boundary(tab,"L_point_pass"),1)
        self.assertEqual(b.confirm_set(tab),[0,1,2,3])
        
if __name__=="__main__":unittest.main()
