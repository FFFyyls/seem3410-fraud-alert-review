"""Deterministic references for shift boundaries, exact labour, and CRN."""
import unittest
import numpy as np
from engine import DAY, Inputs, generate_inputs, simulate
from staffing import DailyWindows, simulate_peak


def fixture(arr,service,horizon=2000):
    return Inputs(arr,np.zeros(len(arr),int),service,horizon)


class StaffingCalendar(unittest.TestCase):
    def test_backlog_at_opening_and_no_new_start_at_closing(self):
        shifts=DailyWindows([(10,20),(30,40)])
        x=fixture([0,0,0,1,2,3],[100,100,100,10,3,12])
        y=simulate_peak(x,0,50,shifts)
        # Fourth seat takes first waiting job at opening without an arrival.
        # Finishes at 20, waits until 30 before taking another. Service 33..45
        # crosses the 40-minute closing. Three permanent seats stay busy.
        np.testing.assert_equal(y.start,[0,0,0,10,30,33])
        np.testing.assert_equal(y.analyst,[0,1,2,3,3,3])
        self.assertEqual((y.scheduled_min,y.overtime_min),(20,5))

    def test_at_exact_open_close_and_regular_preference(self):
        x=fixture([10,10,10,10,20],[15,15,15,10,2])
        y=simulate_peak(x,0,30,DailyWindows([(10,20)]))
        np.testing.assert_equal(y.analyst,[0,1,2,3,0])
        np.testing.assert_equal(y.start,[10,10,10,10,25])
        self.assertEqual(y.overtime_min,0)

    def test_very_long_job_across_next_windows_counted_once_and_clipped(self):
        w=DailyWindows([(10,20),(30,40)])
        # Fourth seat works [10,1500). Next day opens [1450,1460),[1470,1480).
        x=fixture([0,0,0,0],[1600,1600,1600,1490],1800)
        y=simulate_peak(x,15,1475,w)
        self.assertEqual(len(y.ids),0)  # service from before measurement matters
        self.assertEqual(y.scheduled_min,5+10+10+5)
        self.assertEqual(y.overtime_min,(1475-15)-30)
        z=simulate_peak(x,1475,1510,w)
        self.assertEqual((z.scheduled_min,z.overtime_min),(5,20))

    def test_empty_day_pays_idle_coverage(self):
        y=simulate_peak(fixture([],[]),0,DAY,DailyWindows([(600,780),(1080,1260)]))
        self.assertEqual((y.scheduled_min,y.overtime_min),(360,0))

    def test_never_open_and_always_open_match_fixed_engine_and_input_ids(self):
        x=generate_inputs("B",34101594,852,3)
        for cap,win in [(3,[]),(4,[(0,DAY)])]:
            a=simulate_peak(x,DAY,2*DAY,DailyWindows(win))
            b=simulate(x,"DYNAMIC",cap,DAY,2*DAY,20)
            for key in ("ids","start","finish","analyst","risk","arrival"):
                np.testing.assert_equal(getattr(a,key),getattr(b,key))
            np.testing.assert_allclose(a.finish-a.start,x.service[a.ids],rtol=1e-12)
            self.assertEqual((a.scheduled_min,a.overtime_min),((cap-3)*DAY,0))

    def test_actual_windows_against_slow_integer_tick_oracle(self):
        # Finite integer input permits a separate clock-by-clock scheduler.
        rng=np.random.default_rng(773); n=120
        arr=np.sort(rng.integers(0,120,n)); risk=rng.integers(0,3,n); service=rng.integers(2,12,n)
        x=Inputs(arr,risk,service,2000); wins=[(10,30),(55,100),(150,185)]
        y=simulate_peak(x,0,125,DailyWindows(wins))
        pending=set(range(n)); seats=np.zeros(4,int); st=np.zeros(n,int); who=np.zeros(n,int)
        for t in range(400):
            for seat in range(4):
                if seats[seat]>t or (seat==3 and not any(l<=t<u for l,u in wins)):continue
                ready=[j for j in pending if arr[j]<=t]
                if not ready:break
                j=min(ready,key=lambda j:(risk[j]-(t-arr[j])//20,arr[j],j))
                pending.remove(j); st[j]=t; who[j]=seat; seats[seat]=t+service[j]
        self.assertFalse(pending)
        np.testing.assert_equal(y.start,st); np.testing.assert_equal(y.analyst,who)
        ot=sum(any(who[j]==3 and st[j]<=t<st[j]+service[j] for j in range(n))
               and not any(l<=t<u for l,u in wins) for t in range(125))
        self.assertEqual(y.overtime_min,ot)


if __name__=="__main__":
    unittest.main()
