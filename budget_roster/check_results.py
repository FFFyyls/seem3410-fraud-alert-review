"""Audit the frozen decisions, pointwise/simultaneous boundaries, and paired counts."""
import argparse
from collections import defaultdict
import csv,json
from pathlib import Path
import numpy as np
import run_budget as s

def read(p):return list(csv.DictReader(p.open(encoding="utf-8",newline="")))

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out",type=Path,default=s.HERE/"results");p=ap.parse_args().out
    locks=json.loads((p/"locked_rosters.json").read_text(encoding="utf-8"))
    assert [r["budget"] for r in locks]==list(range(25))
    g=defaultdict(list)
    for r in read(p/"training_grid.csv"):
        b=int(r["budget"])
        assert r["rule"]=="DYNAMIC" and int(r["n"])==16
        for m in s.METRICS:
            for suffix in ("","_lo","_hi"):r[m+suffix]=float(r[m+suffix])
        g[b].append(r)
    for item in locks:
        b=item["budget"]; opts=g[b]
        assert len(opts)==item["candidates"] and {r["window"] for r in opts}=={s.key(w) for w in s.space(b)}
        assert s.choose(opts)["window"]==item["window"]
    assert sum(len(x) for x in g.values())==3271
    assert locks[6]["window"]=="11-14/16-19"
    lookup={v["budget"]:v["window"] for v in locks}
    criticals={}
    phase_records={}
    for stem,fname in [("test","budget_frontier"),("confirmation","confirmation")]:
        lv=read(p/(fname+".csv"));rr=read(p/(stem+"_replications.csv"))
        phase_records[stem]=rr
        reported={int(v["budget"]) for v in lv}
        assert reported==(set(range(25)) if stem=="test" else want_confirmation)
        assert len(rr)==len(reported)*80*2
        groups=defaultdict(list);denoms=defaultdict(set)
        for r in rr:
            gk=(r["window"],r["rule"]);groups[gk].append(r)
            assert np.isclose(100*int(r["H_late_n"])/int(r["H_n"]),float(r["H_late_pct"]))
            assert np.isclose(100*int(r["L_long_n"])/int(r["L_n"]),float(r["L_long_pct"]))
            assert float(r["paid_extra_h_day"])>=s.budget(r["window"])-1e-10
            denoms[int(r["rep"])].add((r["H_n"],r["L_n"]))
        assert all(len(x)==1 for x in denoms.values())
        for v in lv:
            b=int(v["budget"]);win=v["window"];assert win==lookup[b]
            arr={}
            for rule in ("DYNAMIC","FCFS"):
                rows=sorted(groups[win,rule],key=lambda r:int(r["rep"]))
                assert [int(r["rep"]) for r in rows]==list(range(80))
                arr[rule]={m:np.array([float(r[m]) for r in rows]) for m in s.METRICS}
            for m,values in arr["DYNAMIC"].items():
                result=s.mean_ci(values)
                assert np.isclose(result["estimate"],float(v[m]))
                assert np.isclose(result["ci_high"],float(v[m+"_hi"]))
            diff=arr["FCFS"]["H_late_pct"]-arr["DYNAMIC"]["H_late_pct"]
            assert np.isclose(s.mean_ci(diff)["ci_low"],float(v["H_reduction_pp_lo"]))
            d=arr["DYNAMIC"]["L_long_pct"]
            upper=float(d.mean()+s.BONF*d.std(ddof=1)/80**.5)
            assert np.isclose(upper,float(v["L_sim_hi"]))
            assert (v["L_sim_pass"]=="True")==(upper<=5)
            assert (v["L_point_pass"]=="True")==(float(v["L_long_pct_hi"])<=5)
            assert (v["joint_daily_pass"]=="True")==((v["L_point_pass"]=="True") and float(v["H_reduction_pp_lo"])>=2)
        if stem=="test":
            calc=[dict(budget=int(v["budget"]),**{k:v[k]=="True" for k in ("L_point_pass","L_sim_pass","joint_daily_pass")}) for v in lv]
            want_confirmation=set(s.confirm_set(calc))
            for k in ("L_point_pass","L_sim_pass","joint_daily_pass"):criticals[k]=s.boundary(calc,k)
            old=next(v for v in read(s.CURVE/"results"/"test_levels.csv") if v["rule"]=="DYNAMIC" and v["a"]=="11" and v["b"]=="16")
            current=next(v for v in lv if v["budget"]=="6")
            for m in s.METRICS:assert np.isclose(float(old[m]),float(current[m]),rtol=0,atol=1e-12)
    passing=criticals["L_point_pass"]
    if passing is not None and passing>0:
        pairs=read(p/"threshold_contrast.csv")
        expected=[v for phase,stem in [("screen","test"),("confirmation","confirmation")] for v in
            s.threshold_contrast(phase_records[stem],lookup[passing-1],lookup[passing],phase)]
        assert len(pairs)==len(expected)
        for v,w in zip(pairs,expected):
            assert (v["phase"],v["metric"],v["reference"],v["alternative"])==(w["phase"],w["metric"],w["reference"],w["alternative"])
            for m in ("estimate","ci_low","ci_high"):assert np.isclose(float(v[m]),w[m])
    print("Verified all training choices, 25 locked test rows, six-hour reference continuity, matched case counts and confirmation.",criticals)

if __name__=="__main__":main()
