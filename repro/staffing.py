"""Verified daily fourth-seat calendar, reused from the original study."""
from dataclasses import dataclass
from math import inf, isfinite
import numpy as np
from engine import DAY, _dispatch

class DailyWindows:
    """Half-open daily windows of the extra seat. No other seat changes."""
    def __init__(self, windows):
        self.windows=tuple((float(l),float(u)) for l,u in windows)
        if any(not 0<=l<u<=DAY for l,u in self.windows) or any(
                b[0]<a[1] for a,b in zip(self.windows,self.windows[1:])):
            raise ValueError("supply sorted non-overlapping intervals within one day")
        self.scheduled_per_day=sum(u-l for l,u in self.windows)

    def next_open(self,t):
        if not self.windows or t==inf: return inf
        day,minute=divmod(t,DAY)
        for left,right in self.windows:
            if minute<right:
                return t if minute>=left else day*DAY+left
        return (day+1)*DAY+self.windows[0][0]

    def select_seat(self,free,gate):
        if not isfinite(gate):return inf,0
        regular=max(gate,min(free[:3]))
        # A regular seat can always be preferred if already free at gate.
        if regular>gate:
            fourth=self.next_open(max(gate,free[3]))
            if fourth<regular:return fourth,3
        return regular,next(k for k in range(3) if free[k]<=regular)

    def scheduled_before(self,t):
        """Lebesgue length of the scheduled set in [0,t); supports arrays."""
        day,phase=np.divmod(t,DAY)
        return day*self.scheduled_per_day+sum(np.clip(phase-l,0,u-l) for l,u in self.windows)


@dataclass
class PeakResult:
    ids:np.ndarray
    risk:np.ndarray
    arrival:np.ndarray
    start:np.ndarray
    finish:np.ndarray
    analyst:np.ndarray
    scheduled_min:float
    overtime_min:float


def simulate_peak(inputs,t0,t1,windows,policy="DYNAMIC",ageing=20):
    """Reuse the fixed engine's event calendar, ordering, cohort and termination."""
    lo,hi,b,d,seat=_dispatch(inputs,policy,4,t0,t1,ageing,select_seat=windows.select_seat)
    extra=seat==3
    left=np.clip(b[extra],t0,t1); right=np.clip(d[extra],t0,t1)
    # For every fourth-seat job, subtract the scheduled overlap from its
    # clipped busy interval. Disjoint nonpreemptive jobs cannot double-count.
    paid_in_shift=windows.scheduled_before(right)-windows.scheduled_before(left)
    overtime=float(np.maximum(0.,right-left-paid_in_shift).sum())
    scheduled=float(windows.scheduled_before(t1)-windows.scheduled_before(t0))
    return PeakResult(np.arange(lo,hi),inputs.risk[lo:hi],inputs.arrival[lo:hi],b[lo:hi],
                      d[lo:hi],seat[lo:hi],scheduled,overtime)
