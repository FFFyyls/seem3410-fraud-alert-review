"""Run the independent pilot, freeze design, then run the 17 fixed comparisons."""
import argparse
import csv
import json
import math
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from analysis import KEY, class_metrics, decide_replications, decide_warmup, display_scale, guardrail, mean_ci, paired, summarize

DAY=1440
PILOT_SEED=34101590
MAIN_SEED=341015
N_PILOT=10
OBS_DAYS=14
POLICIES=('FCFS','STATIC','DYNAMIC')
ENVS=('B','D','C','V','R')
METADATA=('rep','env','policy','config','capacity','ageing_min','extra_followup_days')

def configs(env):
    c=4 if env=='C' else 3
    ret=[(f'{env}_{p}',p,c,20) for p in POLICIES]
    if env=='B': ret += [(f'B_DYNAMIC_A{a}','DYNAMIC',c,a) for a in (10,40)]
    return ret

def save(path, rows):
    if not rows: raise ValueError(f'Empty result: {path}')
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)

def write_json(path, obj):
    path.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def simulate_env(env,seed,rep,t0,t1,selected):
    from engine import generate_inputs,simulate,InsufficientFollowup
    days=math.ceil(t1/DAY)+7
    while True:
        inp=generate_inputs(env,seed,rep,days)
        try:
            runs=[(cid,p,c,a,simulate(inp,p,c,t0,t1,ageing=a)) for cid,p,c,a in selected]
        except InsufficientFollowup:
            days+=7
            continue
        return runs,days-(math.ceil(t1/DAY)+7)

def pilot_worker(rep):
    windows=[]; daily=[]
    for env in ('B','D','R'):
        runs,extra=simulate_env(env,PILOT_SEED,rep,0,28*DAY,configs(env)[:3])
        for cid,p,c,a,r in runs:
            w=r.start-r.arrival; t=r.finish-r.arrival
            for warm in (7,14):
                ix=(r.arrival>=warm*DAY)&(r.arrival<(warm+OBS_DAYS)*DAY)
                metrics=class_metrics(r.risk[ix],w[ix],t[ix])
                windows.append(dict(rep=rep,env=env,policy=p,config=cid,warmup_days=warm,
                                    extra_followup_days=extra,**{k:metrics[k] for k in KEY}))
            for d in r.daily:
                day=int(round(d['time_min']/DAY))
                if not 1<=day<=28: continue
                ix=(r.arrival >= (day-1)*DAY)&(r.arrival<day*DAY)
                hm=ix&(r.risk==0); lm=ix&(r.risk==2)
                daily.append(dict(rep=rep,env=env,policy=p,day=day,waiting=d['waiting'],busy=d['busy'],
                                  total_unfinished=d['waiting']+d['busy'],
                                  H_completion_late=float(np.mean(t[hm]>30)),
                                  L_p95_wait_min=float(np.quantile(w[lm],.95,method='linear'))))
    return windows,daily

def main_worker(args):
    rep,warm=args; rows=[]; daily=[]
    for env in ENVS:
        runs,extra=simulate_env(env,MAIN_SEED,rep,warm*DAY,(warm+OBS_DAYS)*DAY,configs(env))
        for cid,p,c,a,r in runs:
            metric=summarize(r)
            md=dict(rep=rep,env=env,policy=p,config=cid,capacity=c,ageing_min=a if p=='DYNAMIC' else '',extra_followup_days=extra)
            endpoint=None
            for d in r.daily:
                day=int(round(d['time_min']/DAY))
                if not warm<day<=warm+OBS_DAYS: continue
                totals={k:int(d[k]) for k in ('waiting_H','waiting_M','waiting_L','busy_H','busy_M','busy_L','waiting','busy')}
                totals['total_unfinished']=totals['waiting']+totals['busy']
                daily.append(dict(rep=rep,config=cid,measure_day=day-warm,**totals))
                if day==warm+OBS_DAYS: endpoint=totals
            if endpoint is None or metric['end_queue']!=endpoint['waiting']:
                raise ValueError('Measurement endpoint snapshot absent or inconsistent')
            for label in 'HML':
                metric['end_waiting_'+label]=endpoint['waiting_'+label]
                metric['end_busy_'+label]=endpoint['busy_'+label]
            metric['end_total_unfinished']=endpoint['total_unfinished']
            rows.append({**md,**metric})
    return rows,daily

def collect(fn,args,workers):
    start=time.perf_counter(); a=[]; b=[]
    if workers==1:
        for arg in args:
            x,y=fn(arg);a.extend(x);b.extend(y)
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for x,y in pool.map(fn,args,chunksize=1): a.extend(x);b.extend(y)
    return a,b,round(time.perf_counter()-start,2)

def buckets(rows,*keys):
    b=defaultdict(list)
    for r in rows: b[tuple(r[k] for k in keys)].append(r)
    return b

def run_pilot(out,workers):
    win,daily,sec=collect(pilot_worker,range(N_PILOT),workers)
    save(out/'pilot_windows.csv',win);save(out/'pilot_daily.csv',daily)
    by=buckets(win,'config','warmup_days')
    contrasts=[]
    for (cid,warm),rs in by.items():
        if warm==14:
            for metric in (KEY[0],KEY[2]):
                contrasts.append(dict(config=cid,**paired(rs,by[cid,7],metric)))
    chosen=decide_warmup(contrasts)
    save(out/'pilot_warmup_contrasts.csv',contrasts)
    pres=[]
    for alternative in ('B_STATIC','B_DYNAMIC'):
        for metric,target in [(KEY[0],2.),(KEY[2],5.)]:
            p=paired(by[alternative,chosen],by['B_FCFS',chosen],metric)
            nreq=(1.96*p['sd']/target)**2
            pres.append(dict(alternative=alternative,reference='B_FCFS',target_halfwidth=target,unrounded_n=nreq,**p))
    n=decide_replications([r['unrounded_n'] for r in pres])
    save(out/'pilot_precision.csv',pres)
    bm=[]
    for (env,p,day),group in buckets(daily,'env','policy','day').items():
        m={k:float(np.mean([x[k] for x in group])) for k in ('waiting','busy','total_unfinished','H_completion_late','L_p95_wait_min')}
        bm.append(dict(env=env,policy=p,day=day,**m))
    save(out/'pilot_daily_means.csv',bm)
    from pilot_chart import draw
    draw(out/'pilot_diagnostics.html',bm)
    info=dict(pilot_root=PILOT_SEED,pilot_reps=N_PILOT,pilot_envs=['B','D','R'],
              warmup_days=chosen,measurement_days=OBS_DAYS,main_root=MAIN_SEED,
              replications=n,configuration_count=17,main_runs=n*17,initial_followup_days=7,
              pilot_max_extra_followup_days=max(r['extra_followup_days'] for r in win))
    write_json(out/'design_freeze.json',info)
    print('Frozen design:',info, 'pilot wall seconds:',sec,flush=True)
    return info

def summarize_main(out,rows):
    by={k[0]:v for k,v in buckets(rows,'config').items()}
    metrics=[k for k in rows[0] if k not in METADATA]
    levels=[]
    for cid,rs in by.items():
        for m in metrics:
            scale,unit=display_scale(m)
            levels.append(dict(config=cid,metric=m,unit=unit,**mean_ci([r[m]*scale for r in rs])))
    save(out/'levels_ci.csv',levels)
    effects=[]
    def contrast(cid,ref,kind):
        for metric in metrics:
            effects.append(dict(comparison=kind,alternative=cid,reference=ref,**paired(by[cid],by[ref],metric)))
    for env in ENVS:
        for a,b in [('STATIC','FCFS'),('DYNAMIC','FCFS'),('DYNAMIC','STATIC')]:
            contrast(f'{env}_{a}',f'{env}_{b}','within_environment')
    for p in POLICIES: contrast('C_'+p,'B_'+p,'capacity_4_minus_3_same_inputs')
    for a in (10,40):
        for ref in ('B_FCFS','B_DYNAMIC'): contrast(f'B_DYNAMIC_A{a}',ref,'ageing_sensitivity')
    save(out/'paired_effects_ci.csv',effects)
    L={(x['config'],x['metric']):x for x in levels}
    E={(x['alternative'],x['reference'],x['metric']):x for x in effects}
    dec=[]
    for cid,rs in by.items():
        env=rs[0]['env']; ref=env+'_FCFS'
        hi=L[cid,'H_completion_late']; lo=L[cid,'L_wait_gt60']; p95=L[cid,'L_p95_wait_min']
        d=E.get((cid,ref,'H_completion_late'))
        dd=E.get((cid,ref,'L_wait_gt60'))
        dec.append(dict(config=cid,R=hi['n_reps'],capacity=rs[0]['capacity'],
                        H_late_pct=hi['estimate'],H_late_low_pct=hi['ci_low'],H_late_high_pct=hi['ci_high'],
                        H_diff_vs_FCFS_pp=d['estimate'] if d else 0.,H_diff_low_pp=d['ci_low'] if d else 0.,H_diff_high_pp=d['ci_high'] if d else 0.,
                        L_wait_gt60_pct=lo['estimate'],L_guard_low_pct=lo['ci_low'],L_guard_high_pct=lo['ci_high'],
                        L_diff_vs_FCFS_pp=dd['estimate'] if dd else 0.,L_diff_low_pp=dd['ci_low'] if dd else 0.,L_diff_high_pp=dd['ci_high'] if dd else 0.,
                        L_guardrail=guardrail(lo['ci_low'],lo['ci_high']),L_p95_wait_min=p95['estimate'],
                        H_start_by15_pct=L[cid,'H_start_by15']['estimate'],mean_queue=L[cid,'mean_queue']['estimate'],
                        utilization_pct=L[cid,'utilization']['estimate']))
    save(out/'decision_table.csv',dec)

def run_main(out,workers,freeze):
    if freeze['main_root']!=MAIN_SEED or freeze['measurement_days']!=OBS_DAYS:
        raise ValueError('Frozen seed/horizon mismatches this driver')
    n,w=freeze['replications'],freeze['warmup_days']
    rows,daily,sec=collect(main_worker,[(r,w) for r in range(n)],workers)
    if len(rows)!=n*17 or len(daily)!=n*17*OBS_DAYS: raise ValueError('Incomplete configuration or daily matrix')
    save(out/'replication_metrics.csv',rows);save(out/'daily_backlog.csv',daily);summarize_main(out,rows)
    info=dict(replications=n,configurations=17,configuration_replications=len(rows),measurement_days=OBS_DAYS,
              warmup_days=w,root_seed=MAIN_SEED,max_extra_followup_days=max(r['extra_followup_days'] for r in rows),
              workers=workers,wall_seconds=sec,python=sys.version.split()[0],numpy=np.__version__)
    write_json(out/'run_manifest.json',info)
    print('Completed:',info,flush=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['pilot','main','all'],nargs='?',default='all')
    parser.add_argument('--workers',type=int,default=min(6,os.cpu_count() or 1))
    parser.add_argument('--out',type=Path,default=Path(__file__).resolve().parent/'results')
    args=parser.parse_args()
    if args.workers<1:parser.error('--workers must be >=1')
    args.out.mkdir(exist_ok=True,parents=True)
    if args.stage in ('all','pilot'): run_pilot(args.out,args.workers)
    if args.stage in ('all','main'):
        p=args.out/'design_freeze.json'
        if not p.is_file():parser.error('Run pilot first (or use all)')
        run_main(args.out,args.workers,json.loads(p.read_text(encoding='utf-8')))

if __name__=='__main__': main()
