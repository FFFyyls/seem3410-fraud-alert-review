"""Deterministic acceptance tests. Run: python -m unittest -v test_engine"""
import unittest
import numpy as np
from engine import Inputs, InsufficientFollowup, generate_inputs, simulate


def table(a, r, s, horizon=100.):
    return Inputs(np.array(a, dtype=float), np.array(r, dtype=int),
                  np.array(s, dtype=float), horizon)


class EventCalendar(unittest.TestCase):
    def test_fcfs_multiserver_hand_trace(self):
        # Seat 0 takes jobs 0 then 3. Seat 1 takes jobs 1 then 2.
        x = table([0, 0, 1, 2], [2, 0, 1, 0], [5, 3, 3, 2])
        y = simulate(x, "FCFS", 2, 0, 8, audit=True)
        np.testing.assert_equal(y.start, [0, 0, 3, 5])
        np.testing.assert_equal(y.finish, [5, 3, 6, 7])
        np.testing.assert_equal(y.analyst, [0, 1, 1, 0])
        self.assertEqual(y.mean_queue, 5/8)
        self.assertEqual(y.max_queue, 2)
        self.assertEqual(y.utilization, 13/16)

    def test_static_batch_before_dispatch_and_nonpreemption(self):
        # Both completed seats and both new H join the same event batch.
        x = table([0, 0, 1, 5, 5], [2, 2, 1, 0, 0], [5, 5, 4, 1, 3])
        y = simulate(x, "STATIC", 2, 0, 10, audit=True)
        np.testing.assert_equal(y.start, [0, 0, 6, 5, 5])
        np.testing.assert_equal(y.analyst, [0, 1, 0, 0, 1])

    def test_aging_exact_threshold_and_tie_breaks(self):
        for t, expected in [(39.999, [0, 40.999, 39.999]), (40., [0, 40., 42.])]:
            x = table([0, 0, t], [0, 2, 0], [t, 2, 1])
            y = simulate(x, "DYNAMIC", 1, 0, 45, ageing=20, audit=True)
            np.testing.assert_allclose(y.start, expected)

    def test_ageing_matches_independent_full_scan(self):
        # Small independent, intentionally slow oracle; integer clocks force ties.
        rng = np.random.default_rng(272)
        a = np.sort(rng.integers(0, 75, 180))
        r = rng.integers(0, 3, 180)
        s = rng.integers(1, 12, 180)
        for policy in ("FCFS", "STATIC", "DYNAMIC"):
            free = [0, 0, 0]; pending = set(range(len(a)))
            starts = np.zeros(len(a)); assigned = np.zeros(len(a), int)
            while pending:
                now = max(min(free), min(a[j] for j in pending))
                server = next(k for k, until in enumerate(free) if until <= now)
                def key(j):
                    priority = (0 if policy == "FCFS" else r[j] if policy == "STATIC"
                                else r[j] - (now-a[j])//7)
                    return priority, a[j], j
                j = min((j for j in pending if a[j] <= now), key=key)
                starts[j] = now; assigned[j] = server; free[server] = now+s[j]
                pending.remove(j)
            y = simulate(table(a,r,s,1000), policy, 3, 0, 80, 7, audit=True)
            np.testing.assert_equal(y.start, starts)
            np.testing.assert_equal(y.analyst, assigned)

    def test_half_open_cohort_cross_window_area_and_followup_arrival(self):
        # Job 0 spans T0. At T1=6 the measurement cohort contains only job 1.
        # Future H at 6 must overtake that L at time 10 under static priority.
        x = table([0, 4, 6], [1, 2, 0], [10, 3, 2], 20)
        y = simulate(x, "STATIC", 1, 4, 6)
        np.testing.assert_equal(y.ids, [1]); np.testing.assert_equal(y.start, [12])
        np.testing.assert_equal(y.finish, [15])
        self.assertEqual((y.mean_queue,y.max_queue,y.utilization), (1,1,1))
        self.assertEqual((y.backlog_at_end,y.unfinished_at_end), (1,1))

    def test_midnight_left_limit_and_exact_boundary_completion(self):
        x = table([1438, 1439, 1440], [2, 0, 1], [2, 1, 3], 2000)
        y = simulate(x, "FCFS", 1, 0, 1440)
        d, = y.daily
        self.assertEqual((d["waiting_H"],d["busy_L"],d["waiting"],d["busy"]), (1,1,1,1))
        self.assertEqual(y.unfinished_at_end,2)
        self.assertEqual(y.backlog_at_end,1)
        self.assertEqual(y.max_queue,1)
        self.assertAlmostEqual(y.utilization,2/1440)

    def test_empty_cohort_and_idle_seats(self):
        y = simulate(table([0], [0], [10]), "FCFS", 5, 2, 3)
        self.assertEqual(len(y.ids),0); self.assertEqual(y.utilization,.2)
        self.assertEqual(y.unfinished_at_end,0)
        z = simulate(table([], [], []), "FCFS", 1, 0, 10)
        self.assertEqual((z.mean_queue, z.max_queue, z.utilization), (0,0,0))

    def test_incomplete_followup_is_not_silent_draining(self):
        with self.assertRaises(InsufficientFollowup):
            simulate(table([0,1], [2,0], [10,1], 8), "STATIC", 1, 0, 3)
        y = simulate(table([0,1], [2,0], [10,1], 11), "STATIC", 1, 0, 3)
        np.testing.assert_equal(y.finish, [10,11])

    def test_invalid_parameters(self):
        x = table([0], [0], [1])
        for args in [("TYPO",1,0,9,1),("FCFS",0,0,9,1),("DYNAMIC",1,0,9,0),
                     ("FCFS",1,9,9,1),("FCFS",1,0,101,1)]:
            with self.assertRaises(ValueError): simulate(x,*args)
        for a,r,s in [([1,0],[0,1],[1,1]),([0],[3],[1]),([0],[1],[-1])]:
            with self.assertRaises(ValueError): table(a,r,s)


class SyntheticInput(unittest.TestCase):
    def test_crn_across_policies_and_scenarios_and_extension(self):
        b,c,v,r,long,repeat = [generate_inputs(env,341015,3,days)
                               for env,days in [("B",2),("C",2),("V",2),("R",2),("B",4),("B",2)]]
        for other in (c,v,r,repeat): np.testing.assert_equal(b.arrival,other.arrival)
        for other in (c,repeat,long):
            for key in ("arrival","risk","service"):
                np.testing.assert_equal(getattr(b,key),getattr(other,key)[:len(b.arrival)])
        np.testing.assert_equal(b.risk,v.risk)
        self.assertFalse(np.array_equal(b.service,v.service))
        self.assertTrue(np.all(r.risk<=b.risk))
        for policy in ("FCFS","STATIC","DYNAMIC"):
            y = simulate(b,policy,3,0,1440,audit=True)
            np.testing.assert_equal(b.risk[y.ids],y.risk)
            np.testing.assert_allclose(y.finish-y.start,b.service[y.ids],atol=1e-11)
        self.assertFalse(b.arrival.flags.writeable)

    def test_input_boundaries(self):
        z = generate_inputs("B",1,1,2,rates=(0,0,0,0,0))
        self.assertEqual(len(z.arrival),0)
        x = generate_inputs("B",1,1,2,probabilities=(0,0,1),cv=0)
        self.assertTrue(np.all(x.risk==2)); np.testing.assert_allclose(x.service,4.)
        for kwargs in ({"probabilities": (1,1,1)},{"cv":-1},{"means":(0,2,3)},
                       {"rates":(-1,0,0,0,0)}):
            with self.assertRaises(ValueError): generate_inputs("B",1,1,2,**kwargs)


class Theory(unittest.TestCase):
    def test_erlang_c_known_values_and_no_steady_state(self):
        from validation import erlang_c
        ref = erlang_c(22.5,6.8,3)
        for key,value in [("p_wait",.7303766105),("wait_min",11.0368021143),
                          ("mean_queue",4.1388007929),("utilization",.85)]:
            self.assertAlmostEqual(ref[key],value,places=8)
        with self.assertRaises(ValueError): erlang_c(22.5,6.8,2)


if __name__ == "__main__":
    unittest.main()
