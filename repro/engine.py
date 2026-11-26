"""Fraud-alert review DES. All clocks are minutes; arrays are in alert-ID order.

Exactly one event calendar is used for the pilot, production and M/M/3 check.
No policy sees service durations when choosing which waiting alert to start.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import floor, isfinite
from numbers import Integral
import numpy as np

DAY = 1440
LABELS = "HML"
SEGMENTS = (0, 600, 780, 1080, 1260, DAY)


def _positive_int(x):
    return isinstance(x, Integral) and not isinstance(x, bool) and x > 0


@dataclass(frozen=True)
class Inputs:
    arrival: np.ndarray
    risk: np.ndarray     # H=0, M=1, L=2; row index is alert ID
    service: np.ndarray
    horizon_min: float   # all exogenous arrivals are known on [0,horizon_min)

    def __post_init__(self):
        a = np.array(self.arrival, dtype=float, copy=True)
        r = np.asarray(self.risk)
        s = np.array(self.service, dtype=float, copy=True)
        if not (a.ndim == r.ndim == s.ndim == 1 and a.shape == r.shape == s.shape):
            raise ValueError("arrival, risk and service must be aligned 1-D arrays")
        if not isfinite(self.horizon_min) or self.horizon_min <= 0:
            raise ValueError("horizon_min must be finite and positive")
        if (not np.all(np.isfinite(a)) or np.any(a < 0) or np.any(a >= self.horizon_min)
                or np.any(a[1:] < a[:-1])):
            raise ValueError("arrivals must be sorted and in [0,horizon_min)")
        if not np.all(np.isin(r, [0,1,2])):
            raise ValueError("risk must be H=0, M=1 or L=2")
        if not np.all(np.isfinite(s) & (s > 0)):
            raise ValueError("all service times must be finite and positive")
        r = r.astype(np.int8, copy=True)
        for name, arr in (("arrival",a), ("risk",r), ("service",s)):
            arr.setflags(write=False)
            object.__setattr__(self, name, arr)


def generate_inputs(env: str, root_seed: int, rep: int, days: int, *,
                    rates=None, probabilities=None, means=None, cv=None) -> Inputs:
    """Draw a complete input table; extending days preserves every earlier ID.

    PCG64(SeedSequence([root_seed, rep, day_index, stream])) with day_index from
    zero and stream 0=count, 1=within-interval location, 2=risk, 3=service Z.
    B/C/V/R share primitive streams; D has its own within-environment CRN.
    Optional parameters implement input-boundary fixtures, not extra scenarios.
    """
    env = env.upper()
    if env not in ("B","C","D","R","V") or not _positive_int(days):
        raise ValueError("env must be B/C/D/R/V and days a positive integer")
    if any(not isinstance(v, Integral) or v < 0 for v in (root_seed,rep)):
        raise ValueError("root_seed and rep must be non-negative integers")
    rates = np.asarray(rates if rates is not None else
                       np.array([18,36,18,36,18]) * (1.10 if env=="D" else 1), dtype=float)
    p = np.asarray(probabilities if probabilities is not None else
                   ([.3,.3,.4] if env=="R" else [.2,.3,.5]), dtype=float)
    m = np.asarray(means if means is not None else [12,8,4], dtype=float)
    cv = (1.2 if env=="V" else .6) if cv is None else cv
    if rates.shape != (5,) or not np.all(np.isfinite(rates) & (rates >= 0)):
        raise ValueError("provide five nonnegative finite hourly arrival rates")
    if p.shape != (3,) or not np.all(np.isfinite(p) & (p >= 0)) or abs(p.sum()-1) > 1e-12:
        raise ValueError("three risk probabilities must be nonnegative and sum to 1")
    if m.shape != (3,) or not np.all(np.isfinite(m) & (m > 0)) or not isfinite(cv) or cv < 0:
        raise ValueError("conditional means must be positive and CV nonnegative")
    counts_mean = rates*np.diff(SEGMENTS)/60
    sigma2 = np.log1p(cv**2)
    mu = np.log(m)-sigma2/2
    cumulative = np.cumsum(p)[:2]
    arrivals, risks, services = [], [], []
    for day in range(days):
        rng = [np.random.Generator(np.random.PCG64(np.random.SeedSequence(
            [int(root_seed),int(rep),day,stream]))) for stream in range(4)]
        counts = rng[0].poisson(counts_mean)
        a = np.concatenate([np.sort(rng[1].uniform(left,right,int(n)),kind="stable")
                            for n,left,right in zip(counts,SEGMENTS,SEGMENTS[1:])])
        a += day*DAY
        r = np.searchsorted(cumulative, rng[2].random(len(a)), side="right")
        s = np.exp(mu[r] + np.sqrt(sigma2)*rng[3].standard_normal(len(a)))
        arrivals.append(a); risks.append(r); services.append(s)
    return Inputs(np.concatenate(arrivals),np.concatenate(risks),
                  np.concatenate(services),days*DAY)


class InsufficientFollowup(RuntimeError):
    """Extend exogenous input by additional complete days and retry."""


@dataclass
class Result:
    ids: np.ndarray
    risk: np.ndarray
    arrival: np.ndarray
    start: np.ndarray
    finish: np.ndarray
    analyst: np.ndarray  # zero-based seat at dispatch
    mean_queue: float
    utilization: float
    max_queue: int
    backlog_at_end: int  # all waiting Q(T1-), including any pre-warm-up arrivals
    unfinished_at_end: int  # cohort only, not completed at T1-
    daily: list[dict]


def _state_counts(a, b, d, times):
    """Counts immediately before each clock time. Infinite b/d = not started."""
    arrived = np.searchsorted(a, times, side="left")
    started = np.searchsorted(np.sort(b), times, side="left")
    ended = np.searchsorted(np.sort(d), times, side="left")
    return arrived-started, started-ended


def _dispatch(inputs, policy, capacity, t0, t1, ageing, *, audit=False, select_seat=None):
    """Shared dispatch clock for fixed and scheduled-seat experiments.

    Dispatch-clock DES: when all seats are busy, arrivals up to the next free
    time can be enqueued in one batch. This skips no dispatch opportunities.
    Free seats at t include every completion at t, and every arrival <=t
    joins before selection. Use the smallest free seat ID on ties. Financial
    effects, blocking, abandonment and interruptions are outside this model.
    """
    policy = policy.upper()
    if policy not in ("FCFS","STATIC","DYNAMIC"):
        raise ValueError("policy must be FCFS, STATIC or DYNAMIC")
    if not _positive_int(capacity) or not isfinite(ageing) or ageing <= 0:
        raise ValueError("capacity must be a positive integer and ageing positive")
    if not 0 <= t0 < t1 <= inputs.horizon_min:
        raise ValueError("require 0 <= t0 < t1 <= input horizon")
    a,r,s = inputs.arrival.tolist(),inputs.risk.tolist(),inputs.service.tolist()
    n = len(a); inf = float("inf")
    lo,hi = map(int, np.searchsorted(inputs.arrival, [t0,t1], side="left"))
    b,d,analyst = [inf]*n, [inf]*n, [-1]*n
    q = [deque(),deque(),deque()]
    free_at = [0.]*capacity
    i = waiting = cohort_starts = dispatched = 0
    now = 0.
    while True:
        next_arrival = a[i] if i < n else inf
        if select_seat is None:
            t = max(now,min(free_at),now if waiting else next_arrival)
        else:
            # The scheduled path can wake at a shift opening, even when no
            # arrival or service completion occurs. A waiting job is not needed
            # before the opening: all arrivals up to the clock join below.
            t,seat = select_seat(free_at,max(now,now if waiting else next_arrival))
        if t >= t1 and cohort_starts == hi-lo:
            break
        if t >= inputs.horizon_min:
            raise InsufficientFollowup("cohort still waiting at input horizon; extend inputs")
        while i < n and a[i] <= t:
            q[r[i]].append(i); i += 1; waiting += 1
        if select_seat is None:
            seat = next(j for j,u in enumerate(free_at) if u <= t)
        # Within one risk class its oldest alert weakly dominates every younger
        # score and also wins equal scores. Thus only three heads need scoring.
        if policy == "STATIC":
            cls = 0 if q[0] else 1 if q[1] else 2
        elif policy == "FCFS":
            cls = min((queue[0],k) for k,queue in enumerate(q) if queue)[1]
        else:
            cls = min((k - floor((t-a[queue[0]])/ageing),queue[0],k)
                      for k,queue in enumerate(q) if queue)[2]
        j = q[cls].popleft()
        b[j] = t; d[j] = t+s[j]; analyst[j] = seat
        if audit:
            assert d[j] > b[j] >= a[j] and now <= t and free_at[seat] <= t
        free_at[seat] = d[j]; now = t; waiting -= 1
        cohort_starts += lo <= j < hi
        dispatched += 1
        if audit:
            assert waiting == sum(len(z) for z in q) == i-dispatched
    # Once dispatched, a job's completion is fixed by nonpreemption. We require
    # it inside the known external-input horizon even if no more events matter.
    cohort = slice(lo,hi)
    if max(d[cohort], default=0.) > inputs.horizon_min:
        raise InsufficientFollowup("cohort finishes after input horizon; extend inputs")
    return lo,hi,np.asarray(b[:hi]),np.asarray(d[:hi]),np.asarray(analyst[:hi],dtype=int)


def simulate(inputs: Inputs, policy: str, capacity: int, t0: float, t1: float,
             ageing: float = 20, *, audit: bool = False) -> Result:
    """Fixed seats, original contract. No shift calendar or new input required."""
    lo,hi,b0,d0,analyst = _dispatch(inputs,policy,capacity,t0,t1,ageing,audit=audit)
    cohort = slice(lo,hi)
    a0 = inputs.arrival[:hi]; r0 = inputs.risk[:hi]
    span = t1-t0
    # Exact state areas: integrate one customer's waiting/busy indicator, then
    # sum. This also includes pre-t0 arrivals overlapping the measurement window.
    def area(left,right):
        return float(np.maximum(0.,np.minimum(right,t1)-np.maximum(left,t0)).sum())
    mean_q = area(a0,b0)/span
    utilization = area(b0,d0)/(capacity*span)
    starts_sorted = np.sort(b0)
    # Only a batch containing arrivals can increase the queue. Right limits
    # remove every start in that batch; instantaneous pre-dispatch Q is excluded.
    at0 = int(np.searchsorted(a0,t0,"right")-np.searchsorted(starts_sorted,t0,"right"))
    event_q = np.arange(lo+1,hi+1)-np.searchsorted(starts_sorted,a0[lo:hi],"right")
    max_q = int(max(at0,event_q.max(initial=0)))
    q_end = int(hi-np.searchsorted(starts_sorted,t1,"left"))
    unfinished = int(np.count_nonzero(d0[cohort] >= t1))
    # All day boundaries up to t1, including the warm-up for drift diagnostics.
    days = np.arange(1,int(t1//DAY)+1,dtype=int)
    times = days*DAY
    daily = [dict(day=int(k),time_min=int(t),waiting=0,busy=0) for k,t in zip(days,times)]
    for k, label in enumerate(LABELS):
        keep = r0==k
        nq,nb = _state_counts(a0[keep],b0[keep],d0[keep],times)
        for row,x,y in zip(daily,nq,nb):
            row["waiting_"+label]=int(x); row["busy_"+label]=int(y)
            row["waiting"]+=int(x); row["busy"]+=int(y)
    if audit:
        assert 0 <= utilization <= 1+1e-12 and mean_q >= 0
        for row in daily:
            arrived = np.searchsorted(a0,row["time_min"],"left")
            done = np.count_nonzero(d0 < row["time_min"])
            assert arrived == done+row["waiting"]+row["busy"]
            assert row["waiting"] == 0 or row["busy"] == capacity
    return Result(np.arange(lo,hi),r0[cohort],a0[cohort],b0[cohort],
                  d0[cohort],analyst[cohort],
                  mean_q,utilization,max_q,q_end,unfinished,daily)
