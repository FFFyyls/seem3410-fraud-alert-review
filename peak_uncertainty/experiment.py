"""Posted fourth-seat calendars under unpredictable peak starts. Python + NumPy."""
from __future__ import annotations
import argparse, csv, json, sys
from concurrent.futures import ProcessPoolExecutor
from itertools import product
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'repro'))
from analysis import mean_ci
from engine import DAY, Inputs, InsufficientFollowup, generate_inputs
from staffing import DailyWindows, simulate_peak
from study import BASE_EDGES, BASE_RATES

D=json.loads((HERE/'design.json').read_text())
GRID=list(product(D['roster_offsets_min'],repeat=2))
T0=D['warmup_days']*DAY
T1=T0+D['measurement_days']*DAY
METRICS=('H_late_pct','L_long_pct','paid_h_day','L_13_14_pct','L_21_22_pct')

def shift_draws(root,rep,days):
    return np.random.default_rng([root,rep,D['peak_rng_stream']]).uniform(-60.,60.,(days,2))

def change_timing(x,shifts):
    """Invert each day's cumulative intensity; no change to count, risk or work."""
    days=len(shifts)
    if x.horizon_min!=days*DAY or shifts.shape!=(days,2) or not np.all(abs(shifts)<=60):
        raise ValueError('two bounded errors per input day required')
    out=np.empty_like(x.arrival)
    mass=np.r_[0.,np.cumsum(np.diff(BASE_EDGES)*BASE_RATES/60)]
    cuts=np.searchsorted(x.arrival,np.arange(days+1)*DAY)
    for i,(a,b) in enumerate(shifts):
        sl=slice(cuts[i],cuts[i+1]); start=i*DAY
        edges=BASE_EDGES+np.array([0,a,a,b,b,0])
        warped=np.r_[0.,np.cumsum(np.diff(edges)*BASE_RATES/60)]
        out[sl]=start+np.interp(np.interp(x.arrival[sl]-start,BASE_EDGES,mass),warped,edges)
    return Inputs(out,x.risk,x.service,x.horizon_min)

def label(x,y,rule='A20',demand='uncertain'):
    return f'{demand}_{rule}_{x:+d}_{y:+d}'

def run_rep(task):
    root,rep,plans=task
    days=(T1//DAY+D['initial_followup_days'])
    while True:
        orig=generate_inputs('B',root,rep,days)
        jitter=change_timing(orig,shift_draws(root,rep,days))
        rows=[]
        try:
            for x,y,rule,demand in plans:
                inp=jitter if demand=='uncertain' else orig
                a,b=np.array(D['nominal_starts_min'])+[x,y]
                windows=DailyWindows([(a,a+180),(b,b+180)])
                o=simulate_peak(inp,T0,T1,windows,'DYNAMIC' if rule=='A20' else 'FCFS',20)
                h,l=o.risk==0,o.risk==2
                late=o.finish-o.arrival>30.; long=o.start-o.arrival>60.; clock=o.arrival%DAY
                midday=l&(clock>=780)&(clock<840); night=l&(clock>=1260)&(clock<1320)
                rows.append(dict(plan=label(x,y,rule,demand),lunch_offset=x,evening_offset=y,rule=rule,demand=demand,rep=rep,
                    H_n=int(h.sum()),L_n=int(l.sum()),H_late_n=int(late[h].sum()),L_long_n=int(long[l].sum()),
                    H_late_pct=100*late[h].mean(),L_long_pct=100*long[l].mean(),
                    paid_h_day=(o.scheduled_min+o.overtime_min)/60/D['measurement_days'],
                    L_13_14_pct=100*long[midday].mean(), L_21_22_pct=100*long[night].mean(),
                    extra_followup_days=days-T1//DAY-D['initial_followup_days']))
            return rows
        except InsufficientFollowup: days+=7

def levels(rows):
    result=[]
    for key in sorted({r['plan'] for r in rows}):
        group=sorted((r for r in rows if r['plan']==key),key=lambda r:r['rep'])
        record={k:group[0][k] for k in ('plan','lunch_offset','evening_offset','rule','demand')}
        record['reps']=len(group)
        for k in METRICS:
            ci=mean_ci([r[k] for r in group]);record[k]=ci['estimate'];record[k+'_lo']=ci['ci_low'];record[k+'_hi']=ci['ci_high']
        result.append(record)
    return result

def choose(table):
    allowed=[x for x in table if x['L_long_pct_hi']<=5]
    def key(r):
        x,y=r['lunch_offset'],r['evening_offset']
        return ((r['H_late_pct'],r['L_long_pct']) if allowed else (r['L_long_pct'],r['H_late_pct']))+(abs(x)+abs(y),x,y)
    return min(allowed or table,key=key),len(allowed)

def save(path,rows):
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)

def execute(root,reps,plans,workers):
    tasks=[(root,i,plans) for i in range(reps)]
    if workers==1:return [r for t in tasks for r in run_rep(t)]
    with ProcessPoolExecutor(workers) as pool:return [r for chunk in pool.map(run_rep,tasks) for r in chunk]

def pair(rows,comparisons):
    lookup={(r['plan'],r['rep']):r for r in rows}
    result=[]
    for name,left,right in comparisons:
        for k in METRICS:
            ci=mean_ci([lookup[left,i][k]-lookup[right,i][k] for i in sorted({r['rep'] for r in rows})])
            result.append(dict(comparison=name,alternative=left,reference=right,metric=k,
                unit='seat-h/day' if k=='paid_h_day' else 'pp',**ci))
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workers',type=int,default=4);p.add_argument('--out',type=Path,default=HERE/'results');a=p.parse_args()
    if a.workers<1:p.error('--workers must be positive')
    a.out.mkdir(parents=True,exist_ok=True)
    r=execute(D['screen_root'],D['screen_reps'],[(x,y,'A20','uncertain') for x,y in GRID],a.workers)
    tab=levels(r);save(a.out/'screening.csv',tab);save(a.out/'screening_reps.csv',r)
    win,n=choose(tab);x,y=win['lunch_offset'],win['evening_offset']
    lock=dict(selected_lunch_offset_min=x,selected_evening_offset_min=y,n_grid=len(GRID),screened_in=n,training_root=D['screen_root'],holdout_root=D['holdout_root'])
    (a.out/'selection.json').write_text(json.dumps(lock,indent=2)+'\n',encoding='utf-8')
    s=label(x,y);nom=label(0,0);later=label(30,30);early=label(-30,-30);fc=label(x,y,'FCFS');exact=label(0,0,'A20','on_time')
    plans=list(dict.fromkeys([(x,y,'A20','uncertain'),(0,0,'A20','uncertain'),(30,30,'A20','uncertain'),(-30,-30,'A20','uncertain'),(x,y,'FCFS','uncertain'),(0,0,'A20','on_time')]))
    held=execute(D['holdout_root'],D['holdout_reps'],plans,a.workers)
    contrasts=[('selected_minus_nominal',s,nom),('both_30_later_minus_nominal',later,nom),('both_30_earlier_minus_nominal',early,nom),('selected_minus_same_FCFS',s,fc),('peak_uncertainty_at_nominal',nom,exact)]
    save(a.out/'holdout_reps.csv',held);save(a.out/'holdout_levels.csv',levels(held));save(a.out/'holdout_paired.csv',pair(held,contrasts))
    print(lock,flush=True)

if __name__=='__main__': main()
