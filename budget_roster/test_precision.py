import math
import unittest
import numpy as np
import precision as p

def two_sided_t_tail(t,df):
    """Independent check for odd df: integrate cos(theta)**(df-1) by recurrence."""
    theta=math.atan(t/math.sqrt(df)); c=math.cos(theta);s=math.sin(theta)
    at=theta;full=math.pi/2
    for i in range(2,df,2):
        at=(s*c**(i-1)+(i-1)*at)/i
        full=(i-1)*full/i
    return 1-at/full

class PrecisionDesignTests(unittest.TestCase):
    def test_quantiles_against_independent_tail(self):
        self.assertAlmostEqual(two_sided_t_tail(p.POINT,p.N-1),.05,places=12)
        self.assertAlmostEqual(two_sided_t_tail(p.SIM,p.N-1),.05/3,places=12)
    def test_fixed_size_and_intervals(self):
        with self.assertRaises(ValueError):p.interval([1,2,3])
        with self.assertRaises(ValueError):p.interval([float("nan")]*p.N)
        x=np.arange(p.N);m,l,u=p.interval(x)
        self.assertAlmostEqual(m,599.5)
        self.assertAlmostEqual((u-l)/2,p.POINT*math.sqrt((p.N+1)/12))
        _,ls,us=p.interval(x,p.SIM)
        self.assertLess(ls,l);self.assertGreater(us,u)
if __name__=="__main__":unittest.main()
