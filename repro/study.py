"""Independent matched-input demand-timing and equal-duration staffing study."""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor
import csv
import json
from pathlib import Path
import sys
import time
import numpy as np
from analysis import class_metrics, mean_ci
from engine import DAY, Inputs, InsufficientFollowup, generate_inputs, simulate
from staffing import DailyWindows, simulate_peak

HERE=Path(__file__).resolve().parent
DESIGN=json.loads((HERE/'study_design.json').read_text(encoding='utf-8'))
BASE_EDGES=np.array([0,600,780,1080,1260,1440.])
BASE_RATES=np.array([18,36,18,36,18.])
PROB=('H_completion_late','L_wait_gt60','H_start_by15',
      'L_wait_gt60_arrive_13_14','L_wait_gt60_arrive_21_22')
HOURS=('extra_scheduled_h_day','extra_overtime_h_day','extra_paid_h_day','total_paid_h_day')
METRICS=PROB+('L_p95_wait_min',)+HOURS
COMPARISONS=(('shift30_A20','peak_A20'),('peak_A20','fixed3_A20'),
             ('shift30_A20','fixed3_A20'),('fixed4_A20','fixed3_A20'),
             ('peak_A20','fixed4_A20'),('shift30_A20','fixed4_A20'),
             ('peak_A20','peak_FCFS'),('shift30_A20','shift30_FCFS'))


def remap_inputs(base, edges, rates):
    """Preserve every daily alert ID and mark, change only NHPP intensity shape.

    Lambda_target(arrival_new) = Lambda_baseline(arrival_old), day by day.
    Both daily integrated intensities must be 540. Zero-rate intervals are skipped.
    """
    edges=np.asarray(edges,dtype=float);rates=np.asarray(rates,dtype=float)
    if (edges.ndim!=1 or rates.shape!=(len(edges)-1,) or edges[0]!=0 or edges[-1]!=DAY
            or np.any(np.diff(edges)<=0) or not np.all(np.isfinite(rates)&(rates>=0))):
        raise ValueError('invalid daily intensity profile')
    cumulative=np.r_[0.,np.cumsum(rates*np.diff(edges)/60)]
    if not np.isclose(cumulative[-1],DESIGN['expected_alerts_per_day'],atol=1e-9,rtol=0):
        raise ValueError('daily integrated intensity must remain 540')
    day,phase=np.divmod(base.arrival,DAY)
    old_cum=np.r_[0.,np.cumsum(BASE_RATES*np.diff(BASE_EDGES)/60)]
    old_index=np.searchsorted(BASE_EDGES,phase,side='right')-1
    volume=old_cum[old_index]+(phase-BASE_EDGES[old_index])*BASE_RATES[old_index]/60
    index=np.searchsorted(cumulative,volume,side='right')-1
    new=edges[index]+(volume-cumulative[index])*60/rates[index]
    return Inputs(day*DAY+new,base.risk,base.service,base.horizon_min)


def proxy_hourly_rates(rows,phase_shift_hours=0):
    counts=np.zeros(24);exposure=np.zeros(24)
    for row in rows:
        h=int(row['hour']);n=float(row['count']);t=float(row['exposure_seconds'])
        if not 0<=h<24 or n<0 or not 0<t<=3600 or not np.isfinite(n+t):
            raise ValueError('invalid hourly count or observed exposure')
        counts[h]+=n;exposure[h]+=t
    if np.any(exposure<=0) or counts.sum()<=0:
        raise ValueError('proxy must cover all 24 relative hours with positive total counts')
    rate=counts/exposure
    return np.roll(rate/rate.sum()*DESIGN['expected_alerts_per_day'],int(phase_shift_hours))


def profiles(include_proxy=False):
    out={'synthetic_base':(BASE_EDGES.tolist(),BASE_RATES.tolist()),
         'synthetic_delay60':([0,660,840,1140,1320,1440],BASE_RATES.tolist())}
    if include_proxy:
        with (HERE/'data'/'hourly_profile.csv').open(encoding='utf-8-sig',newline='') as f:
            rows=list(csv.DictReader(f))
        for shift in (0,12):
            out[f'proxy_phase{shift}']=(list(range(0,1441,60)),proxy_hourly_rates(rows,shift).tolist())
    return out


def arrival_metrics(risk,arrival,wait,duration):
    met=class_metrics(risk,wait,duration)
    for name,left in [('13_14',780),('21_22',1260)]:
        keep=(risk==2)&(arrival%DAY>=left)&(arrival%DAY<left+60)
        met[f'L_arrive_{name}_n']=int(keep.sum())
        met[f'L_wait_gt60_arrive_{name}']=float(np.mean(wait[keep]>60)) if keep.any() else float('nan')
    return met


def decision_gates(aggregate_upper,first_upper,second_upper,h_difference_upper):
    aggregate=aggregate_upper<=DESIGN['aggregate_L_limit_pct']
    windows=max(first_upper,second_upper)<=DESIGN['new_fixed_window_L_limit_pct']
    benefit=h_difference_upper<=-DESIGN['same_schedule_H_reduction_benchmark_pp']
    return dict(aggregate_pass=bool(aggregate),fixed_windows_pass=bool(windows),
                H_benefit_pass=bool(benefit),protected_candidate=bool(aggregate and windows and benefit))


def run_plan(x,plan,t0,t1):
    policy='FCFS' if plan.endswith('FCFS') else 'DYNAMIC'
    if plan.startswith('fixed'):
        c=3 if plan.startswith('fixed3') else 4
        y=simulate(x,policy,c,t0,t1,DESIGN['ageing_min'])
        return y,24.*(c-3),0.
    windows=DESIGN['shifted_windows_min'] if plan.startswith('shift30') else DESIGN['original_windows_min']
    y=simulate_peak(x,t0,t1,DailyWindows(windows),policy,DESIGN['ageing_min'])
    days=(t1-t0)/DAY
    return y,y.scheduled_min/(60*days),y.overtime_min/(60*days)


def replicate(args):
    rep,profile_map=args
    warm=DESIGN['warmup_days'];length=DESIGN['measurement_days']
    t0,t1=warm*DAY,(warm+length)*DAY
    extra=0
    while True:
        base=generate_inputs('B',DESIGN['root_seed'],rep,warm+length+DESIGN['initial_followup_days']+extra)
        rows=[];cohort_ids=None
        try:
            for scenario,(edges,rates) in profile_map.items():
                x=remap_inputs(base,edges,rates)
                for plan in DESIGN['plans']:
                    y,scheduled,overtime=run_plan(x,plan,t0,t1)
                    if cohort_ids is None:cohort_ids=y.ids
                    if not np.array_equal(y.ids,cohort_ids):raise AssertionError('paired cohort ID mismatch')
                    met=arrival_metrics(y.risk,y.arrival,y.start-y.arrival,y.finish-y.arrival)
                    row=dict(scenario=scenario,study_scope='exploratory_proxy' if scenario.startswith('proxy') else 'prespecified_synthetic',
                             rep=rep,root_seed=DESIGN['root_seed'],plan=plan,extra_followup_days=extra,
                             **{k:met[k] for k in ('H_n','M_n','L_n','L_arrive_13_14_n','L_arrive_21_22_n')},
                             **{k:met[k] for k in PROB+('L_p95_wait_min',)},
                             extra_scheduled_h_day=scheduled,extra_overtime_h_day=overtime,
                             extra_paid_h_day=scheduled+overtime,total_paid_h_day=72+scheduled+overtime)
                    rows.append(row)
            return rows
        except InsufficientFollowup:extra+=7


def scaled(metric,difference=False):
    if metric in PROB:return 100.,'pp' if difference else '%'
    return 1.,'min' if metric.endswith('_min') else 'seat-h/day'


def summarize(rows):
    grouped={}
    for row in rows:
        g=grouped.setdefault((row['scenario'],row['plan']),{})
        if row['rep'] in g:raise ValueError('duplicate replication')
        g[row['rep']]=row
    expected=set(range(DESIGN['replications']))
    if any(set(g)!=expected for g in grouped.values()):raise ValueError('incomplete paired study')
    scenarios=list(dict.fromkeys(r['scenario'] for r in rows));levels=[];effects=[];decisions=[]
    for scenario in scenarios:
        scope='exploratory_proxy' if scenario.startswith('proxy') else 'prespecified_synthetic'
        for plan in DESIGN['plans']:
            for metric in METRICS:
                scale,unit=scaled(metric)
                levels.append(dict(scenario=scenario,study_scope=scope,plan=plan,metric=metric,unit=unit,
                    **mean_ci([scale*grouped[scenario,plan][r][metric] for r in sorted(expected)])))
        for alt,ref in COMPARISONS:
            for metric in METRICS:
                scale,unit=scaled(metric,True)
                effects.append(dict(scenario=scenario,study_scope=scope,alternative=alt,reference=ref,metric=metric,unit=unit,
                    **mean_ci([scale*(grouped[scenario,alt][r][metric]-grouped[scenario,ref][r][metric]) for r in sorted(expected)])))
        l={(r['plan'],r['metric']):r for r in levels if r['scenario']==scenario}
        e={(r['alternative'],r['reference'],r['metric']):r for r in effects if r['scenario']==scenario}
        for plan,fcfs in [('peak_A20','peak_FCFS'),('shift30_A20','shift30_FCFS')]:
            guards=[l[plan,k]['ci_high'] for k in ('L_wait_gt60','L_wait_gt60_arrive_13_14','L_wait_gt60_arrive_21_22')]
            h=e[plan,fcfs,'H_completion_late']['ci_high']
            decisions.append(dict(scenario=scenario,study_scope=scope,plan=plan,
                aggregate_L_upper_pct=guards[0],original_close_13_upper_pct=guards[1],original_close_21_upper_pct=guards[2],
                H_vs_same_schedule_FCFS_upper_pp=h,**decision_gates(*guards,h)))
    return levels,effects,decisions


def warmup_check(args):
    rep,profile_map=args;rows=[];days=35
    while True:
        base=generate_inputs('B',DESIGN['root_seed'],rep,days)
        try:
            for scenario,(edges,rates) in profile_map.items():
                x=remap_inputs(base,edges,rates);offset=int(np.searchsorted(x.arrival,7*DAY))
                short=Inputs(x.arrival[offset:],x.risk[offset:],x.service[offset:],x.horizon_min)
                for plan in DESIGN['plans']:
                    long,_,_=run_plan(x,plan,14*DAY,28*DAY);small,_,_=run_plan(short,plan,14*DAY,28*DAY)
                    assert np.array_equal(long.ids,small.ids+offset)
                    delta=np.abs(long.start-small.start)
                    rows.append(dict(scenario=scenario,rep=rep,plan=plan,
                                     differing_starts=int(np.count_nonzero(delta>1e-8)),max_abs_start_change_min=float(delta.max(initial=0))))
            return rows
        except InsufficientFollowup:days+=7;rows=[]


def save(path,rows):
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--include-proxy',action='store_true');p.add_argument('--workers',type=int,default=8)
    p.add_argument('--out',type=Path,default=HERE/'results');p.add_argument('--check-warmup',action='store_true')
    a=p.parse_args()
    if a.workers<1:p.error('--workers must be positive')
    profile_map=profiles(a.include_proxy);a.out.mkdir(parents=True,exist_ok=True)
    (a.out/'frozen_design.json').write_text(json.dumps(DESIGN,indent=2)+'\n',encoding='utf-8')
    profile_rows=[dict(scenario=sc,left_min=l,right_min=u,rate_per_hour=r) for sc,(ed,ra) in profile_map.items() for l,u,r in zip(ed,ed[1:],ra)]
    save(a.out/'input_profiles.csv',profile_rows)
    start=time.perf_counter();tasks=[(r,profile_map) for r in range(DESIGN['replications'])]
    if a.workers==1:rows=[row for task in tasks for row in replicate(task)]
    else:
        with ProcessPoolExecutor(a.workers) as pool:rows=[row for group in pool.map(replicate,tasks) for row in group]
    levels,effects,decisions=summarize(rows)
    for name,table in [('replications',rows),('levels',levels),('paired',effects),('decisions',decisions)]:save(a.out/f'{name}.csv',table)
    if a.check_warmup:
        tasks=[(r,profile_map) for r in range(10)]
        if a.workers==1:check=[row for task in tasks for row in warmup_check(task)]
        else:
            with ProcessPoolExecutor(a.workers) as pool:check=[row for group in pool.map(warmup_check,tasks) for row in group]
        save(a.out/'warmup_checks.csv',check)
    manifest=dict(root_seed=DESIGN['root_seed'],replications=DESIGN['replications'],scenarios=list(profile_map),
                  plans=DESIGN['plans'],simulation_runs=len(rows),warmup_days=DESIGN['warmup_days'],measurement_days=DESIGN['measurement_days'],
                  max_extra_followup_days=max(r['extra_followup_days'] for r in rows),wall_seconds=time.perf_counter()-start,
                  python=sys.version.split()[0],numpy=np.__version__,workers=a.workers,
                  uncertainty='Monte Carlo conditional on fixed assumed inputs; proxy is exploratory')
    (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(manifest,indent=2))
    for row in decisions:print(row)


if __name__=='__main__':main()
