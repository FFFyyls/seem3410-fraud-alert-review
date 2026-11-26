"""Optimise one fixed roster per budget on one curve, lock all, and test on the next."""
from __future__ import annotations
import argparse, csv, json, os, sys, time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np
from collections import defaultdict

HERE=Path(__file__).resolve().parent
CURVE=HERE.parent/"curve_roster"
sys.path.insert(0,str(CURVE))
import run_study as prior
from engine import generate_inputs, InsufficientFollowup, DAY
from study import remap_inputs
from staffing import DailyWindows, simulate_peak
from analysis import mean_ci
from run_study import profile, save

TRAIN,TEST,CONFIRM=34102641,34102642,34102643
WARM,MEAS,FOLLOW=14,14,7
METRICS=("H_late_pct","L_long_pct","paid_extra_h_day")
BONF=3.196628436099664 # Student t quantile, df=79, two-sided alpha=0.05/25

def space(b):
    if b not in range(25):raise ValueError("Budget must be one of 0..24")
    if b==0:return [()]
    rosters={((a,a+b),) for a in range(25-b)}
    if b>1:
        m=b//2;n=b-m
        for u,v in {(m,n),(n,m)}:
            for a in range(25-b):
                for k in range(a+u+1,25-v):rosters.add(((a,a+u),(k,k+v)))
    return sorted(rosters)

def key(win):
    return "/".join(f"{a:02d}-{b:02d}" for a,b in win) or "off"

def parse(k):
    return () if k=="off" else tuple(tuple(map(int,block.split("-"))) for block in k.split("/"))

def replay(task):
    # Each task reuses one case stream across all its plans.
    rep,seed,rates,plans=task
    days=WARM+MEAS+FOLLOW
    while True:
        base=generate_inputs("B",seed,rep,days)
        x=remap_inputs(base,np.arange(0,DAY+1,60),rates)
        rows=[]
        try:
            for win,rule in plans:
                plan=DailyWindows([(60*a,60*b) for a,b in win])
                y=simulate_peak(x,WARM*DAY,(WARM+MEAS)*DAY,plan,rule,20.)
                H=y.risk==0; L=y.risk==2
                h=int(np.count_nonzero(y.finish[H]-y.arrival[H]>30))
                l=int(np.count_nonzero(y.start[L]-y.arrival[L]>60))
                Hn=int(H.sum());Ln=int(L.sum())
                rows.append((key(win),rule,rep,Hn,Ln,h,l,100*h/Hn,100*l/Ln,(y.scheduled_min+y.overtime_min)/(60*MEAS)))
            return rows
        except InsufficientFollowup:days+=7

FIELDS=("window","rule","rep","H_n","L_n","H_late_n","L_long_n")+METRICS

def simulate_all(executor,seed,n,rates,plans,batch):
    jobs=[(rep,seed,rates,plans[j:j+batch]) for rep in range(n) for j in range(0,len(plans),batch)]
    it=executor.map(replay,jobs) if executor else map(replay,jobs)
    rows=[dict(zip(FIELDS,v)) for vv in it for v in vv];return rows

def levels(rr):
    g=defaultdict(list)
    for r in rr:g[r["window"],r["rule"]].append(r)
    out=[]
    for (window,rule),grp in sorted(g.items()):
        v=dict(window=window,rule=rule,n=len(grp))
        for m in METRICS:
            stats=mean_ci([r[m] for r in grp])
            for prefix,k in [("","estimate"),("_lo","ci_low"),("_hi","ci_high")]:v[m+prefix]=stats[k]
            if m=="L_long_pct" and len(grp)==80:
                v["L_sim_lo"]=stats["estimate"]-BONF*stats["se"];v["L_sim_hi"]=stats["estimate"]+BONF*stats["se"]
        out.append(v)
    return out

def budget(k):
    return sum(b-a for a,b in parse(k))

def choose(vs):
    passing=[v for v in vs if v["L_long_pct_hi"]<=5.]
    def order(v):
        h,l=v["H_late_pct"],v["L_long_pct"]
        return (h,l,parse(v["window"])) if passing else ((h+l)/2,h,l,parse(v["window"]))
    return min(passing or vs,key=order)

def import_six():
    with (CURVE/"results"/"training_grid.csv").open(newline="",encoding="utf-8") as f: rows=list(csv.DictReader(f))
    out=[]
    for r in rows:
        a,b=int(r["a"]),int(r["b"])
        k=key(((a,b+3),) if a+3==b else ((a,a+3),(b,b+3)))
        v=dict(window=k,rule="DYNAMIC",n=int(r["n"]))
        for m in METRICS:
            for tgt,src in [("",""),("_lo","_ci_low"),("_hi","_ci_high")]:v[m+tgt]=float(r[m+src])
        out.append(v)
    if len(out)!=190 or {v["window"] for v in out}!={key(w) for w in space(6)}:
        raise ValueError("Six-hour archive does not match candidate grid")
    return out

def table(locks,rows):
    lv={(v["window"],v["rule"]):v for v in levels(rows)}
    lookup={(v["window"],v["rule"],v["rep"]):v for v in rows}
    result=[]
    for b,win in locks.items():
        k=key(win);v=lv[k,"DYNAMIC"];fc=lv[k,"FCFS"]
        effect=mean_ci([lookup[k,"FCFS",i]["H_late_pct"]-lookup[k,"DYNAMIC",i]["H_late_pct"] for i in range(80)])
        result.append(dict(budget=b,window=k,**{m:v[m] for m in v if m not in ("rule","window")},
            FCFS_H_late_pct=fc["H_late_pct"],H_reduction_pp=effect["estimate"],
            H_reduction_pp_lo=effect["ci_low"],H_reduction_pp_hi=effect["ci_high"],
            L_point_pass=v["L_long_pct_hi"]<=5.,L_sim_pass=v["L_sim_hi"]<=5.,
            joint_daily_pass=(v["L_long_pct_hi"]<=5. and effect["ci_low"]>=2.)))
    return result

def boundary(tab,field):
    return next((r["budget"] for r in tab if r[field]),None)

def confirm_set(tab):
    budgets=set()
    for f in ("L_point_pass","L_sim_pass","joint_daily_pass"):
        k=boundary(tab,f);k=24 if k is None else k;budgets.update([k,max(0,k-1)])
    return sorted(budgets)

def threshold_contrast(records, below, at, phase):
    """Pointwise within-replication effects of funding the first passing hour."""
    g={k:{int(v["rep"]):v for v in records if v["rule"]=="DYNAMIC" and v["window"]==k}
       for k in (below,at)}
    return [dict(phase=phase,alternative=at,reference=below,metric=m,**mean_ci([
        float(g[at][i][m])-float(g[below][i][m]) for i in range(80)])) for m in METRICS]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workers",type=int,default=min(12,os.cpu_count() or 1))
    p.add_argument("--out",type=Path,default=HERE/"results")
    a=p.parse_args();dest=a.out
    if not 1<=a.workers<=12:p.error("workers must be 1–12")
    dest.mkdir(parents=True,exist_ok=True)
    pool=ProcessPoolExecutor(a.workers) if a.workers>1 else None
    started=time.perf_counter()
    try:
        train_rates=profile(0)
        plans=[(win,"DYNAMIC") for b in range(25) if b!=6 for win in space(b)]
        train=levels(simulate_all(pool,TRAIN,16,train_rates,plans,28))+import_six()
        groups=defaultdict(list)
        for r in train:groups[budget(r["window"])].append(r)
        train=sorted(train,key=lambda v:(budget(v["window"]),v["window"]))
        save(dest/"training_grid.csv",[dict(budget=budget(v["window"]),**v) for v in train])
        selected={b:choose(groups[b]) for b in range(25)}
        locks={b:parse(v["window"]) for b,v in selected.items()}
        lockdata=[dict(budget=b,window=selected[b]["window"],candidates=len(groups[b]),
            training_H_pct=selected[b]["H_late_pct"],training_L_pct=selected[b]["L_long_pct"],
            training_L_hi=selected[b]["L_long_pct_hi"],num_training_L_pass=sum(v["L_long_pct_hi"]<=5. for v in groups[b])) for b in range(25)]
        (dest/"locked_rosters.json").write_text(json.dumps(lockdata,indent=2)+"\n",encoding="utf-8")
        print(f"Locked {len(locks)} rosters after {time.perf_counter()-started:.1f} sec", flush=True)
        test_rates=profile(1) # only after locking the entire frontier
        plans=[(w,rule) for w in locks.values() for rule in ("DYNAMIC","FCFS")]
        rr=simulate_all(pool,TEST,80,test_rates,plans,50)
        tab=table(locks,rr);save(dest/"budget_frontier.csv",tab);save(dest/"test_replications.csv",rr)
        print("First passes:",{f:boundary(tab,f) for f in ("L_point_pass","L_sim_pass","joint_daily_pass")},flush=True)
        subset={k:locks[k] for k in confirm_set(tab)}
        plans=[(w,rule) for w in subset.values() for rule in ("DYNAMIC","FCFS")]
        rc=simulate_all(pool,CONFIRM,80,test_rates,plans,50)
        save(dest/"confirmation.csv",table(subset,rc));save(dest/"confirmation_replications.csv",rc)
        first=boundary(tab,"L_point_pass")
        if first is not None and first>0:
            below,at=key(locks[first-1]),key(locks[first])
            save(dest/"threshold_contrast.csv",threshold_contrast(rr,below,at,"screen")+threshold_contrast(rc,below,at,"confirmation"))
        print("Confirmed budgets:",list(subset),"elapsed",round(time.perf_counter()-started,1),flush=True)
    finally:
        if pool:pool.shutdown()

if __name__=="__main__":main()
