"""Supplement the overlapping-window pilot with a same-calendar initialization check.

Empty the short-history model at day 7, retain the long-history model from day
0, and expose both to *identical* calendars from day 7 onward. Measure exactly
the same arrivals on days 15-28. This diagnostic does not set main-run R.
"""
from argparse import ArgumentParser
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np
from engine import Inputs, InsufficientFollowup, generate_inputs, simulate
from analysis import class_metrics
from run_experiments import DAY, N_PILOT, PILOT_SEED, configs, save

def compare(rep):
    rows=[]
    for env in ('B','D','R'):
        days=35
        while True:
            x=generate_inputs(env,PILOT_SEED,rep,days)
            offset=int(np.searchsorted(x.arrival,7*DAY))
            short=Inputs(x.arrival[offset:],x.risk[offset:],x.service[offset:],x.horizon_min)
            current=[]
            try:
                for cid,p,c,a in configs(env)[:3]:
                    y=simulate(x,p,c,14*DAY,28*DAY,ageing=a)
                    z=simulate(short,p,c,14*DAY,28*DAY,ageing=a)
                    if not np.array_equal(y.ids,z.ids+offset) or not np.array_equal(y.arrival,z.arrival):
                        raise ValueError('Mismatched measurement arrivals')
                    delta=y.start-z.start
                    u=class_metrics(y.risk,y.start-y.arrival,y.finish-y.arrival)
                    v=class_metrics(z.risk,z.start-z.arrival,z.finish-z.arrival)
                    current.append(dict(rep=rep,env=env,config=cid,n_cohort=len(delta),
                                       starts_differing_gt_1e_8_min=int(np.count_nonzero(abs(delta)>1e-8)),
                                       max_abs_start_change_min=float(np.max(abs(delta))),
                                       H_completion_late_long_minus_short_pp=(u['H_completion_late']-v['H_completion_late'])*100,
                                       L_p95_wait_long_minus_short_min=u['L_p95_wait_min']-v['L_p95_wait_min']))
                break
            except InsufficientFollowup:
                days+=7
        rows+=current
    return rows

if __name__=='__main__':
    p=ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,default=Path(__file__).resolve().parent/'results')
    p.add_argument('--workers',type=int,default=6);args=p.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    if args.workers==1: rows=[r for i in range(N_PILOT) for r in compare(i)]
    else:
        with ProcessPoolExecutor(args.workers) as pool: rows=[r for group in pool.map(compare,range(N_PILOT)) for r in group]
    save(args.out/'pilot_matched_calendar.csv',rows)
    changed=sum(row['starts_differing_gt_1e_8_min']>0 for row in rows)
    largest=max(row['max_abs_start_change_min'] for row in rows)
    print(f'{changed}/{len(rows)} paired pilot configurations with a changed measurement start; max change {largest:.8g} minutes')
