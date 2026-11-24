"""Independent, fixed four-seat confirmation. One-factor environments, no selection."""
from argparse import ArgumentParser
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from time import perf_counter
from analysis import guardrail, mean_ci, paired
from run_experiments import DAY, save, simulate_env, summarize, write_json, buckets

SEED=34101593
R=100
METRICS=('H_completion_late','L_wait_gt60')

def replicate(rep):
    rows=[]
    for env in ('B','D','V','R'):
        cfg=[(f'{env}4_{p}',p,4,20) for p in ('FCFS','DYNAMIC')]
        runs,extra=simulate_env(env,SEED,rep,7*DAY,21*DAY,cfg)
        for cid,p,c,a,run in runs:
            o=summarize(run)
            rows.append(dict(rep=rep,env=env,config=cid,policy=p,capacity=c,ageing_min=a if p=='DYNAMIC' else '',
                             extra_followup_days=extra,H_completion_late=o['H_completion_late'],
                             L_wait_gt60=o['L_wait_gt60'],H_n=o['H_n'],L_n=o['L_n']))
    return rows

def run(out,workers):
    t0=perf_counter()
    if workers==1:rows=[r for i in range(R) for r in replicate(i)]
    else:
        with ProcessPoolExecutor(workers) as pool: rows=[r for rs in pool.map(replicate,range(R)) for r in rs]
    if len(rows)!=800:raise ValueError('Incomplete independent confirmation')
    save(out/'capacity_followup_replications.csv',rows)
    b=buckets(rows,'env','policy');levels=[];diff=[]
    for env in ('B','D','V','R'):
        for p in ('FCFS','DYNAMIC'):
            for m in METRICS:
                stats=mean_ci([100*r[m] for r in b[env,p]])
                levels.append(dict(env=env,c=4,policy=p,metric=m,unit='%',**stats,
                                   guardrail=guardrail(stats['ci_low'],stats['ci_high']) if m=='L_wait_gt60' else ''))
        for m in METRICS:
            diff.append(dict(env=env,c=4,alternative='DYNAMIC',reference='FCFS',**paired(b[env,'DYNAMIC'],b[env,'FCFS'],m)))
    save(out/'capacity_followup_levels.csv',levels);save(out/'capacity_followup_paired.csv',diff)
    write_json(out/'capacity_followup_manifest.json',dict(root_seed=SEED,replications=R,configs=8,total_runs=800,
               warmup_days=7,measurement_days=14,initial_followup_days=7,
               max_extra_followup_days=max(r['extra_followup_days'] for r in rows),
               workers=workers,wall_seconds=round(perf_counter()-t0,2)))
    for x in levels:
        print(f"{x['env']} {x['policy']:7s} {x['metric']:18s} {x['estimate']:.2f} [{x['ci_low']:.2f},{x['ci_high']:.2f}] {x['guardrail']}")
    for x in diff:
        print(f"{x['env']} DYNAMIC-FCFS {x['metric']:18s} {x['estimate']:.2f} [{x['ci_low']:.2f},{x['ci_high']:.2f}] pp")

if __name__=='__main__':
    p=ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,default=Path(__file__).resolve().parent/'results')
    p.add_argument('--workers',type=int,default=6);a=p.parse_args()
    if a.workers<1:p.error('--workers must be positive')
    a.out.mkdir(exist_ok=True,parents=True); run(a.out,a.workers)

