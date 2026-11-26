"""Risk and handling time: a paired counterfactual on unchanged daily workloads."""
import argparse
import csv
import sys
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "repro"))
from engine import DAY, Inputs, generate_inputs, InsufficientFollowup
from staffing import DailyWindows, simulate_peak
from analysis import mean_ci

SEED = 34101611
N = 100
WARM = 14
MEASURE = 14
WINDOWS = DailyWindows([(600,780),(1080,1260)])
OUTCOMES = ("H_late_pct","L_long_pct")

def shuffle_daily(x, rep):
    """Use a separate stream per day so lengthening follow-up cannot alter history."""
    s = x.service.copy()
    cuts = np.searchsorted(x.arrival, np.arange(0, x.horizon_min+DAY, DAY))
    for d, (lo,hi) in enumerate(zip(cuts, cuts[1:])):
        rng = np.random.default_rng(np.random.SeedSequence([SEED,rep,d,77]))
        s[lo:hi] = rng.permutation(x.service[lo:hi])
    return Inputs(x.arrival, x.risk, s, x.horizon_min)

def budget(daily_cases, mean_minutes, scheduled_hours):
    load = daily_cases * mean_minutes / 60
    return load, load - scheduled_hours

def replicate(rep):
    extra = 7
    while True:
        x = generate_inputs("B",SEED,rep,WARM+MEASURE+extra)
        rows = []
        try:
            for coupling, cases in (("linked",x), ("permuted",shuffle_daily(x,rep))):
                for policy in ("FCFS","DYNAMIC"):
                    z = simulate_peak(cases,WARM*DAY,(WARM+MEASURE)*DAY,WINDOWS,policy)
                    h,l = z.risk==0,z.risk==2
                    rows.append(dict(rep=rep,coupling=coupling,policy=policy,
                        H_late_pct=100*np.mean((z.finish-z.arrival)[h]>30),
                        L_long_pct=100*np.mean((z.start-z.arrival)[l]>60),
                        H_service_mean_min=np.mean(cases.service[z.ids][h]),followup_days=extra))
        except InsufficientFollowup:
            extra += 7
            continue
        return rows

def write_csv(file,rows):
    with file.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

def run(out,workers):
    out.mkdir(parents=True,exist_ok=True)
    with ProcessPoolExecutor(workers) as pool:
        rows=[v for r in pool.map(replicate, range(N),chunksize=4) for v in r]
    write_csv(out/"coupling_reps.csv",rows)
    index={(r["rep"],r["coupling"],r["policy"]):r for r in rows}
    summary=[]
    for metric in OUTCOMES:
        delta={}
        for c in ("linked","permuted"):
            levels={p:np.array([index[(i,c,p)][metric] for i in range(N)]) for p in ("FCFS","DYNAMIC")}
            delta[c]=levels["DYNAMIC"]-levels["FCFS"]
            for name,arr in {**levels, "A20_minus_FCFS":delta[c]}.items():
                summary.append(dict(metric=metric,coupling=c,comparison=name,unit="pp" if name=="A20_minus_FCFS" else "%",**mean_ci(arr)))
        summary.append(dict(metric=metric,coupling="permuted_minus_linked",comparison="change_in_A20_minus_FCFS",unit="pp",**mean_ci(delta["permuted"]-delta["linked"])))
    write_csv(out/"coupling_summary.csv",summary)
    loads=[]
    for s in (6.8,7.6,10,15):
        for h in (72,78,96):
            req,gap=budget(540,s,h)
            loads.append(dict(alerts_day=540,mean_minutes=s,scheduled_seat_h_day=h,
                required_seat_h_day=round(req,3),demand_minus_scheduled_h=round(gap,3),
                ceiling_min_per_alert=round(h*60/540,4)))
    write_csv(out/"capacity_arithmetic.csv",loads)

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers",type=int,default=4)
    parser.add_argument("--out",type=Path,default=HERE/"results")
    args=parser.parse_args()
    run(args.out,args.workers)
