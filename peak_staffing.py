"""Compare A20 + three staffing plans on paired synthetic input. See --help."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
import json
from math import inf, isfinite
from pathlib import Path
import numpy as np
from analysis import class_metrics, guardrail, mean_ci
from engine import DAY, InsufficientFollowup, _dispatch, generate_inputs, simulate
from run_experiments import save, write_json

HERE=Path(__file__).resolve().parent
DESIGN=json.loads((HERE/"results"/"peak_staffing_design.json").read_text(encoding="utf-8"))
PRIMARY=("H_completion_late","L_wait_gt60")
HOURS=("extra_scheduled_h_day","extra_overtime_h_day","extra_paid_h_day","total_paid_h_day")
POST=("L_wait_gt60_arrive_13_14","L_wait_gt60_arrive_21_22")


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


def replicate(args):
    env,rep,mode=args
    plans=("peak4_FCFS",) if mode=="secondary" else DESIGN["plans"]
    day0=DESIGN["warmup_days"]; length=DESIGN["measurement_days"]
    t0,t1=day0*DAY,(day0+length)*DAY
    scheduled=DailyWindows(DESIGN["fourth_seat_windows_min"])
    seed=DESIGN["root_seeds"][env]; extra_days=0
    while True:
        x=generate_inputs(env,seed,rep,day0+length+DESIGN["initial_followup_days"]+extra_days)
        rows=[]; first=None
        try:
            for plan in plans:
                policy="FCFS" if plan=="peak4_FCFS" else "DYNAMIC"
                if plan in ("fixed3","fixed4"):
                    seats=3 if plan=="fixed3" else 4
                    y=simulate(x,policy,seats,t0,t1,DESIGN["ageing_min"])
                    sch=24.*(seats-3); ot=0.
                else:
                    y=simulate_peak(x,t0,t1,scheduled,policy,DESIGN["ageing_min"])
                    sch=y.scheduled_min/(60*length); ot=y.overtime_min/(60*length)
                if first is not None and not np.array_equal(first,y.ids):
                    raise ValueError("occupancy plans used different cohort IDs")
                first=y.ids
                wait=y.start-y.arrival; met=class_metrics(y.risk,wait,y.finish-y.arrival)
                row=dict(env=env,rep=rep,root_seed=seed,plan=plan,policy=policy,
                         extra_followup_days=extra_days,H_n=met["H_n"],L_n=met["L_n"],
                         **{k:met[k] for k in PRIMARY},extra_scheduled_h_day=sch,
                         extra_overtime_h_day=ot,extra_paid_h_day=sch+ot,
                         total_paid_h_day=72+sch+ot)
                # Same fixed IDs in each plan. These diagnostic subsets are
                # defined by ARRIVAL time, not service time or queue at closing.
                for k,l in zip(POST,(780,1260)):
                    ix=(y.risk==2)&(y.arrival%DAY>=l)&(y.arrival%DAY<l+60)
                    row[k]=float(np.mean(wait[ix]>60)) if ix.any() else float("nan")
                    row[k+"_n"]=int(ix.sum())
                rows.append(row)
        except InsufficientFollowup:
            extra_days+=7;continue
        return rows


def rows_for(env,mode,workers):
    tasks=[(env,r,mode) for r in range(DESIGN["replications"])]
    if workers==1:return [row for task in tasks for row in replicate(task)]
    with ProcessPoolExecutor(workers) as executor:
        return [row for result in executor.map(replicate,tasks,chunksize=3) for row in result]


def scale_unit(m,diff=False):
    return ((100.,"pp" if diff else "%") if m in (*PRIMARY,*POST) else (1.,"seat-h/day"))


def summarize(env,rows):
    by={}
    for r in rows:
        group=by.setdefault(r["plan"],{})
        if r["rep"] in group:raise ValueError("duplicate paired key")
        group[r["rep"]]=r
    expected=set(range(DESIGN["replications"]))
    if any(set(group)!=expected for group in by.values()):raise ValueError("missing replication")
    levels=[]; paired=[]
    for plan,group in by.items():
        metrics=PRIMARY+HOURS+(POST if env=="B" and plan in ("peak4","fixed4") else ())
        for m in metrics:
            s,unit=scale_unit(m)
            ci=mean_ci([s*r[m] for r in group.values()])
            levels.append(dict(env=env,plan=plan,metric=m,unit=unit,**ci,
                               guardrail=guardrail(ci["ci_low"],ci["ci_high"]) if m=="L_wait_gt60" else ""))
    comparisons=[("peak4","fixed3"),("peak4","fixed4"),("fixed4","fixed3")]
    if "peak4_FCFS" in by: comparisons.append(("peak4","peak4_FCFS"))
    for alt,base in comparisons:
        metrics=PRIMARY+HOURS+(POST if env=="B" and (alt,base)==("peak4","fixed4") else ())
        for m in metrics:
            s,unit=scale_unit(m,True)
            ci=mean_ci([s*(by[alt][i][m]-by[base][i][m]) for i in sorted(expected)])
            paired.append(dict(env=env,alternative=alt,reference=base,metric=m,unit=unit,**ci))
    return levels,paired


def run(env,out,workers):
    rows=rows_for(env,"primary",workers)
    levels,paired=summarize(env,rows)
    passed=next(r["guardrail"] for r in levels if r["plan"]=="peak4" and r["metric"]=="L_wait_gt60")=="meets"
    if env=="B" and passed:
        rows+=rows_for(env,"secondary",workers)
        levels,paired=summarize(env,rows)
    prefix="peak_staffing_"+env+"_"
    for name,table in [("replications",rows),("levels",levels),("paired",paired)]:
        save(out/(prefix+name+".csv"),table)
    write_json(out/(prefix+"manifest.json"),dict(environment=env,root_seed=DESIGN["root_seeds"][env],
        replications=DESIGN["replications"],plans=list(dict.fromkeys(r["plan"] for r in rows)),
        scenario_runs=len(rows),max_extra_followup_days=max(r["extra_followup_days"] for r in rows),
        peak4_guardrail_met=passed,secondary_FCFS_run=env=="B" and passed))
    for r in levels:
        if r["metric"] in (*PRIMARY,"extra_paid_h_day"):
            print(f"{env} {r['plan']:10} {r['metric']:20} {r['estimate']:.3f} [{r['ci_low']:.3f},{r['ci_high']:.3f}] {r['unit']} {r['guardrail']}")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env",choices=("B","D","R","all"),default="all")
    parser.add_argument("--workers",type=int,default=6)
    parser.add_argument("--out",type=Path,default=HERE/"results")
    a=parser.parse_args()
    if a.workers<1:parser.error("workers must be positive")
    a.out.mkdir(parents=True,exist_ok=True)
    for env in (("B","D","R") if a.env=="all" else (a.env,)):
        run(env,a.out,a.workers)
