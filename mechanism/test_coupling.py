import unittest
import numpy as np
from coupling import shuffle_daily, Inputs, DAY, budget

class AllocationTest(unittest.TestCase):
    def test_same_pool_each_day_not_same_assignment(self):
        arrival = np.r_[np.arange(9.), DAY+np.arange(7.)]; risk=np.arange(16)%3
        x=Inputs(arrival,risk,np.arange(1.,17.),2*DAY)
        y=shuffle_daily(x,12)
        np.testing.assert_array_equal(y.risk,risk); np.testing.assert_array_equal(x.arrival,y.arrival)
        for ix in (slice(0,9),slice(9,16)):
            np.testing.assert_array_equal(np.sort(y.service[ix]),x.service[ix]); self.assertFalse(np.array_equal(y.service[ix],x.service[ix]))
        z=shuffle_daily(Inputs(arrival[:9],risk[:9],x.service[:9],DAY),12)
        np.testing.assert_array_equal(z.service,y.service[:9])
    def test_budget(self):
        self.assertEqual(budget(540,10,78),(90,12)); self.assertEqual(budget(540,15,96),(135,39))
