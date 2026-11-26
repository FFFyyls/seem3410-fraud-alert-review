"""A fresh fixed-size study of the three locked rosters at the budget boundary."""
import argparse,csv,json,os
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import run_budget as b

D=json.loads((b.HERE/"precision_design.json").read_text(encoding="utf-8"))
N=D["replications"];POINT=D["pointwise_t975"];SIM=D["simultaneous_L_t"]
assert N==1200 and D["df"]==N-1

def interval(values,t=POINT):
    x=np.asarray(values,dtype=float)
    if x.shape!=(N,) or not np.isfinite(x).all():raise ValueError("Need 1200 complete independent replications")
    mu=float(x.mean());se=float(x.std(ddof=1)/np.sqrt(N))
    return mu,mu-t*se,mu+t*se

def emit(row,name,vals,t=POINT):
    mu,lo,hi=interval(vals,t)
    row.update({name:mu,name+"_lo":lo,name+"_hi":hi})

def summarize(records,schedules):
    lv=[];effects=[];arrays={}
    for h,w in schedules.items():
        v={"budget":h,"window":w,"n":N}
        g={}
        for rule in ("DYNAMIC","FCFS"):
            rows=sorted([r for r in records if r["window"]==w and r["rule"]==rule],key=lambda r:int(r["rep"]))
            if [int(r["rep"]) for r in rows]!=list(range(N)):raise ValueError("Incomplete paired rows")
            g[rule]={m:np.asarray([float(r[m]) for r in rows]) for m in b.METRICS}
        a,fc=g["DYNAMIC"],g["FCFS"];arrays[h]=a
        for m in b.METRICS:emit(v,m,a[m])
        _,v["L_sim_lo"],v["L_sim_hi"]=interval(a["L_long_pct"],SIM)
        emit(v,"FCFS_H_late_pct",fc["H_late_pct"]);emit(v,"H_reduction_pp",fc["H_late_pct"]-a["H_late_pct"])
        v.update(L_sim_pass=v["L_sim_hi"]<=5.,L_sim_exceeds=v["L_sim_lo"]>5.,H_same_roster_pass=v["H_reduction_pp_lo"]>=2.)
        lv.append(v)
    for alt,ref in [(12,11),(13,12),(13,11)]:
        for m in b.METRICS:
            v=dict(alternative_h=alt,reference_h=ref,metric=m);emit(v,"change",arrays[alt][m]-arrays[ref][m]);effects.append(v)
    return lv,effects

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--workers",type=int,default=min(12,os.cpu_count() or 1))
    p.add_argument("--out",type=Path,default=b.HERE/"results")
    p.add_argument("--locks",type=Path,default=b.HERE/"results"/"locked_rosters.json")
    a=p.parse_args()
    if not 1<=a.workers<=12:p.error("workers must be 1–12")
    schedules={int(h):w for h,w in D["windows"].items()}
    locks={r["budget"]:r["window"] for r in json.loads(a.locks.read_text(encoding="utf-8"))}
    if any(schedules[h]!=locks[h] for h in schedules):raise ValueError("Precision study must use existing first-day locks")
    rates=b.profile(1);plans=[(b.parse(w),rule) for w in schedules.values() for rule in ("DYNAMIC","FCFS")]
    if a.workers>1:
        with ProcessPoolExecutor(a.workers) as pool:r=b.simulate_all(pool,D["root_seed"],N,rates,plans,6)
    else:r=b.simulate_all(None,D["root_seed"],N,rates,plans,6)
    lv,e=summarize(r,schedules);a.out.mkdir(parents=True,exist_ok=True)
    b.save(a.out/"precision_replications.csv",r);b.save(a.out/"precision_levels.csv",lv);b.save(a.out/"precision_paired.csv",e)
    print("New root",D["root_seed"],"independent replications",N,"DES replays",len(r),flush=True)
    for v in lv:print(v["budget"],v["L_long_pct"],(v["L_sim_lo"],v["L_sim_hi"]),v["L_sim_pass"],flush=True)

if __name__=="__main__":main()
