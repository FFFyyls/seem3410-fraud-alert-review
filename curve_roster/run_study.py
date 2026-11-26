"""Select a six-hour fourth-seat schedule from day 1; evaluate on untouched day 2."""
from __future__ import annotations
import argparse
import csv
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import sys
import numpy as np

HERE = Path(__file__).resolve().parent
REPRO = HERE.parent / "repro"
sys.path.insert(0, str(REPRO))
from analysis import mean_ci
from engine import DAY, InsufficientFollowup, generate_inputs
from staffing import DailyWindows, simulate_peak
from study import proxy_hourly_rates, remap_inputs

D = json.loads((HERE / "design.json").read_text(encoding="utf-8"))
METRICS = ("H_late_pct", "L_long_pct", "equal_class_score_pct", "paid_extra_h_day")

def candidate_pairs():
    return [(a, b) for a in range(22) for b in range(a + 3, 22)]

def profile(day):
    with (REPRO / "data" / "hourly_profile.csv").open(newline="", encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if int(r["day"]) == day]
    if sorted(int(r["hour"]) for r in rows) != list(range(24)):
        raise ValueError("Expected 24 distinct observed bins for the selected day")
    return proxy_hourly_rates(rows)

def workload_captured(rates, ab):
    a, b = ab
    return sum(rates[a:a + 3]) + sum(rates[b:b + 3])

def windows(a, b):
    if (a, b) not in PAIRS: raise ValueError("Schedule outside feasibility grid")
    if b == a + 3: return DailyWindows([(a * 60, (b + 3) * 60)])
    return DailyWindows([(a * 60, (a + 3) * 60), (b * 60, (b + 3) * 60)])

PAIRS = set(candidate_pairs())

def replicate(task):
    rep, seed, rates, plans = task
    w, n = D["warmup_days"], D["measure_days"]
    t0, t1 = w*DAY, (w+n)*DAY
    days = w + n + D["initial_followup_days"]
    while True:
        x = remap_inputs(generate_inputs("B", seed, rep, days), np.arange(0, DAY+1, 60), rates)
        rows = []
        try:
            for a,b,rule in plans:
                y = simulate_peak(x, t0, t1, windows(a,b), rule, 20.)
                h = y.risk==0
                l = y.risk==2
                hlate = int(np.count_nonzero((y.finish[h]-y.arrival[h])>30.))
                llong = int(np.count_nonzero((y.start[l]-y.arrival[l])>60.))
                hp = 100.*hlate/h.sum()
                lp = 100.*llong/l.sum()
                rows.append(dict(rep=rep, seed=seed, a=a,b=b,rule=rule,H_n=h.sum(),L_n=l.sum(),
                    H_late_n=hlate,L_long_n=llong,H_late_pct=hp,L_long_pct=lp,
                    equal_class_score_pct=(hp+lp)/2,
                    paid_extra_h_day=(y.scheduled_min+y.overtime_min)/(60*n)))
            return rows
        except InsufficientFollowup:
            days += 7

def stats(rows):
    groups = {}
    for row in rows:
        groups.setdefault((row["a"],row["b"],row["rule"]),[]).append(row)
    out=[]
    for (a,b,rule),rr in sorted(groups.items()):
        v=dict(a=a,b=b,rule=rule,n=len(rr))
        for metric in METRICS:
            m=mean_ci([r[metric] for r in rr])
            for key in ("estimate","ci_low","ci_high"):
                v[metric+("" if key=="estimate" else "_"+key)]=m[key]
        out.append(v)
    return out

def choose(levels):
    passing = [v for v in levels if v["L_long_pct_ci_high"] <= D["guardrail_low_pct"]]
    keys = ("H_late_pct","L_long_pct","a","b") if passing else ("equal_class_score_pct","H_late_pct","L_long_pct","a","b")
    return min(passing or levels,key=lambda v:tuple(v[k] for k in keys))

def select(levels,rates):
    pair=lambda v:(v["a"],v["b"])
    return {"selected":pair(choose(levels)),
            "original":(10,18),
            "best_contiguous":pair(choose([v for v in levels if v["a"]+3==v["b"]])),
            "highest_demand":min(candidate_pairs(),key=lambda s:(-workload_captured(rates,s),*s)),
            "H_only":pair(min(levels,key=lambda v:(v["H_late_pct"],v["L_long_pct"],*pair(v)))),
            "L_only":pair(min(levels,key=lambda v:(v["L_long_pct"],v["H_late_pct"],*pair(v))))}

def paired(rows,roles):
    lookup={(r["rep"],r["a"],r["b"],r["rule"]):r for r in rows}
    reps=sorted(set(r["rep"] for r in rows))
    a,b=roles["selected"]
    contrasts=[(key,*pair,"DYNAMIC") for key,pair in roles.items() if key!="selected"]
    contrasts.append(("same_roster_FCFS",a,b,"FCFS"))
    result=[]
    for label,x,y,rule in contrasts:
        for m in METRICS:
            vals=[lookup[i,a,b,"DYNAMIC"][m] - lookup[i,x,y,rule][m] for i in reps]
            result.append(dict(alternative="selected",reference=label,metric=m,**mean_ci(vals)))
    return result

def save(path,rows):
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workers",type=int,default=4)
    p.add_argument("--out",type=Path,default=HERE/"results")
    args=p.parse_args()
    if not 1<=args.workers<=4: p.error("Use 1–4 workers")
    args.out.mkdir(parents=True,exist_ok=True)
    def run(pool,rates,n,seed,plans):
        tasks=[(i,seed,rates,plans) for i in range(n)]
        return [r for rr in (pool.map(replicate,tasks) if pool else map(replicate,tasks)) for r in rr]
    pool = ProcessPoolExecutor(args.workers) if args.workers>1 else None
    try:
        train_rates=profile(D["training_day"])
        train=run(pool,train_rates,D["training_reps"],D["training_seed"],[(a,b,"DYNAMIC") for a,b in candidate_pairs()])
        levels=stats(train);roles=select(levels,train_rates)
        for v in levels:
            v["expected_alerts_during_blocks"]=workload_captured(train_rates,(v["a"],v["b"]))
        save(args.out/"training_grid.csv",levels)
        (args.out/"locked_rosters.json").write_text(json.dumps(roles,indent=2)+"\n",encoding="utf-8")
        print("Locked",roles,flush=True)
        # The held-out day is first read after rosters are frozen.
        test_rates=profile(D["test_day"])
        plans=sorted(set((*s,"DYNAMIC") for s in roles.values())|{(*roles["selected"],"FCFS")})
        test=run(pool,test_rates,D["test_reps"],D["test_seed"],plans)
    finally:
        if pool: pool.shutdown()
    save(args.out/"test_replications.csv",test)
    save(args.out/"test_levels.csv",stats(test))
    save(args.out/"test_paired.csv",paired(test,roles))
    save(args.out/"profiles.csv",[dict(relative_hour=h,training_rate=train_rates[h],test_rate=test_rates[h]) for h in range(24)])
    print("Completed",len(train),"training and",len(test),"test replays.", flush=True)
if __name__=="__main__": main()
