"""M/M/3 benchmark and a deterministic trace. Run: python validation.py"""
import argparse
import csv
from math import factorial, sqrt
from pathlib import Path
import numpy as np
from engine import DAY, Inputs, generate_inputs, simulate

ROOT = 34101591   # separate from both pilot and production roots
REPS, WARM, COUNT = 10, 20_000, 100_000
T975_DF9 = 2.2621571628540993


def erlang_c(arrivals_per_hour, mean_service_min, capacity):
    """FCFS M/M/c steady state; Wq in minutes, Lq in alerts."""
    lam = arrivals_per_hour/60; mu = 1/mean_service_min
    offered = lam/mu; rho = offered/capacity
    if not (0 < rho < 1) or capacity < 1:
        raise ValueError("Erlang C requires positive stable load and capacity")
    tail = offered**capacity/(factorial(capacity)*(1-rho))
    pw = tail / (sum(offered**k/factorial(k) for k in range(capacity))+tail)
    wq = pw/(capacity*mu-lam)
    return dict(p_wait=pw,wait_min=wq,mean_queue=lam*wq,utilization=rho)


def replicate(rep):
    # Exponential interarrival and service streams; no class structure or peaks.
    # The extra arrival after the input's final row defines a known input horizon.
    gen = lambda stream: np.random.Generator(np.random.PCG64(
        np.random.SeedSequence([ROOT,rep,stream])))
    a = gen(0).exponential(60/22.5,WARM+COUNT+2048+1).cumsum()
    table = Inputs(a[:-1],np.zeros(len(a)-1,dtype=np.int8),
                   gen(1).exponential(6.8,len(a)-1),a[-1])
    y = simulate(table,"FCFS",3,a[WARM],a[WARM+COUNT])
    wait = y.start-y.arrival
    assert len(wait)==COUNT
    return dict(root_seed=ROOT,rep=rep,warm_count=WARM,measurement_count=COUNT,
                p_wait=float(np.mean(wait>0)),wait_min=float(np.mean(wait)),
                mean_queue=y.mean_queue,utilization=y.utilization)


def write_rows(path, rows):
    with path.open("w",newline="",encoding="utf-8") as f:
        out = csv.DictWriter(f,fieldnames=rows[0].keys())
        out.writeheader(); out.writerows(rows)


def input_audit(out):
    """Check the input implementation against its assumptions, not bank data."""
    days = 365
    rows = []
    for env in ("B","D","V","R"):  # C is bit-for-bit B; tested in test_engine.
        x = generate_inputs(env,34101592,0,days)
        phase = x.arrival % DAY
        peak = ((600 <= phase)&(phase < 780)) | ((1080 <= phase)&(phase < 1260))
        def record(metric,group,unit,target,realized,n):
            rows.append(dict(env=env,root_seed=34101592,days=days,metric=metric,
                             group=group,unit=unit,assumed=target,sampled=realized,alerts=n))
        for mask,group,hours,rate in [(peak,"peak",6,36),(~peak,"normal",18,18)]:
            n = int(mask.sum())
            record("arrival_rate",group,"alerts/h",rate*(1.1 if env=="D" else 1),n/(days*hours),n)
        probs = (.3,.3,.4) if env=="R" else (.2,.3,.5)
        for k,(group,p,m) in enumerate(zip("HML",probs,(12,8,4))):
            s = x.service[x.risk==k]
            record("risk_share",group,"proportion",p,len(s)/len(x.arrival),len(s))
            record("service_mean",group,"min",m,float(s.mean()),len(s))
            record("service_cv",group,"ratio",1.2 if env=="V" else .6,
                   float(s.std(ddof=1)/s.mean()),len(s))
    write_rows(out/"validation_synthetic_inputs.csv",rows)


def run(out):
    out.mkdir(parents=True,exist_ok=True)
    input_audit(out)
    ref = erlang_c(22.5,6.8,3)
    rows = [replicate(r) for r in range(REPS)]
    write_rows(out/"validation_replications.csv",rows)
    summary = []
    for key,theory in ref.items():
        obs = [r[key] for r in rows]
        est = float(np.mean(obs)); se = float(np.std(obs,ddof=1)/sqrt(REPS))
        lo,hi = est-T975_DF9*se,est+T975_DF9*se
        error = abs(est-theory)
        tol = (max(3*se,.03*theory) if key=="wait_min" else
               max(3*se,.01) if key=="p_wait" else None)
        summary.append(dict(metric=key,theory=theory,simulation_mean=est,
                            mc_se=se,ci95_low=lo,ci95_high=hi,
                            contains_theory=(lo<=theory<=hi),absolute_error=error,
                            tolerance=tol,criterion_pass=(error<=tol if tol is not None else "")))
    write_rows(out/"validation_summary.csv",summary)
    # Re-readable hand trace. All starts and seat choices are independently
    # predictable by inspection; measured area Q=5 alert-min, B=13 seat-min.
    x = Inputs(np.array([0,0,1,2]),np.array([2,0,1,0]),np.array([5,3,3,2]),100)
    y = simulate(x,"FCFS",2,0,8,audit=True)
    expected = [(0,0,5),(1,0,3),(1,3,6),(0,5,7)]
    trace=[]
    for j,(seat,b,d) in enumerate(expected):
        assert (seat,b,d)==(y.analyst[j],y.start[j],y.finish[j])
        trace.append(dict(id=j,arrival=x.arrival[j],risk="HML"[x.risk[j]],
                          service_min=x.service[j],expected_seat=seat,actual_seat=y.analyst[j],
                          expected_start=b,actual_start=y.start[j],
                          expected_finish=d,actual_finish=y.finish[j]))
    write_rows(out/"validation_hand_trace.csv",trace)
    for row in summary:
        print("{metric:12} theory={theory:.7f} sim={simulation_mean:.7f} "
              "95%CI=[{ci95_low:.7f}, {ci95_high:.7f}]".format(**row))
    if any(row["criterion_pass"] is False for row in summary):
        raise RuntimeError("pre-specified M/M/3 numerical check failed; inspect rather than reseeding")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",type=Path,default=Path(__file__).resolve().parent/"results")
    run(p.parse_args().out)
