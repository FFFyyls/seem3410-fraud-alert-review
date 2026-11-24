"""Audit archived CSVs independently of the simulation and analysis functions."""
import argparse
import csv
import json
from collections import defaultdict
from math import fsum, isclose, sqrt
from pathlib import Path
from statistics import stdev

def load(path):
    with path.open(encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))
def near(x,y):
    if not isclose(float(x),float(y),abs_tol=1e-9,rel_tol=1e-11):
        raise AssertionError(f'{x} differs from {y}')
def ci100(seq, row):
    if len(seq)!=100 or int(row['n_reps'])!=100:raise AssertionError('Unexpected interval sample size')
    mu=fsum(seq)/100;h=1.9842169515864174*stdev(seq)/sqrt(100)
    for k,v in [('estimate',mu),('ci_low',mu-h),('ci_high',mu+h),('halfwidth',h)]:near(row[k],v)
def audit(out):
    if not __debug__: raise RuntimeError('Run the audit without Python -O')
    raw=load(out/'replication_metrics.csv'); follow=load(out/'capacity_followup_replications.csv')
    freeze=json.loads((out/'design_freeze.json').read_text())
    assert (freeze['warmup_days'],freeze['measurement_days'],freeze['replications'],freeze['configuration_count'])==(7,14,100,17)
    assert json.loads((out/'capacity_followup_manifest.json').read_text())['root_seed']==34101593
    index={(r['config'],int(r['rep'])):r for r in raw}
    assert len(index)==len(raw)==1700
    for r in raw:
        for c in 'HML':
            assert int(r[c+'_n'])>0
            near(float(r[c+'_completion_ontime'])+float(r[c+'_completion_late']),1)
            for s in ('completion_late','completion_ontime'):
                assert 0<=float(r[c+'_'+s])<=1
            for point in ('mean','p95'):
                assert 0<=float(r[f'{c}_{point}_wait_min'])<=float(r[f'{c}_{point}_completion_min'])
        assert 0<=float(r['utilization'])<=1 and 0<=float(r['mean_queue'])<=int(r['max_queue'])
        assert int(r['unfinished_cohort_at_end'])<=int(r['end_total_unfinished'])
        assert 0<=float(r['L_wait_gt60'])<=1 and 0<=float(r['H_start_by15'])<=1
        assert int(r['extra_followup_days'])==0
        base=index[(r['env']+'_FCFS',int(r['rep']))]
        for c in 'HML': assert r[c+'_n']==base[c+'_n']
    days=load(out/'daily_backlog.csv')
    assert len({(r['rep'],r['config'],r['measure_day']) for r in days})==len(days)==23800
    for d in days:
        r=index[(d['config'],int(d['rep']))]
        assert 1<=int(d['measure_day'])<=14
        assert sum(int(d['waiting_'+c]) for c in 'HML')==int(d['waiting'])
        assert sum(int(d['busy_'+c]) for c in 'HML')==int(d['busy'])<=int(r['capacity'])
        assert int(d['waiting'])+int(d['busy'])==int(d['total_unfinished'])
        if int(d['waiting']):assert int(d['busy'])==int(r['capacity'])
        if int(d['measure_day'])==14:assert d['total_unfinished']==r['end_total_unfinished']

    # Recalculate published estimates and pointwise intervals from raw rows.
    for x in load(out/'levels_ci.csv'):
        scale=100 if x['unit']=='%' else 1
        ci100([float(index[(x['config'],i)][x['metric']])*scale for i in range(100)],x)
    for x in load(out/'paired_effects_ci.csv'):
        scale=100 if x['unit']=='pp' else 1
        vals=[scale*(float(index[x['alternative'],i][x['metric']])-float(index[x['reference'],i][x['metric']])) for i in range(100)]
        ci100(vals,x)
    fidx={(r['env'],r['policy'],int(r['rep'])):r for r in follow}
    assert len(follow)==len(fidx)==800 and all(int(r['H_n'])>0 and int(r['L_n'])>0 for r in follow)
    for x in load(out/'capacity_followup_levels.csv'):
        vals=[float(fidx[x['env'],x['policy'],i][x['metric']])*100 for i in range(100)]
        ci100(vals,x)
    for x in load(out/'capacity_followup_paired.csv'):
        vals=[100*(float(fidx[x['env'],x['alternative'],i][x['metric']])-float(fidx[x['env'],x['reference'],i][x['metric']])) for i in range(100)]
        ci100(vals,x)

    ex=load(out/'example_alerts.csv')
    assert len(ex)==550 and len(set(r['alert_id'] for r in ex))==550
    for r in ex:
        for p in ('FCFS','STATIC','DYNAMIC'):
            assert float(r['arrival_min'])<=float(r[p+'_start_min'])
            near(float(r[p+'_finish_min'])-float(r[p+'_start_min']),r['service_min'])
    matched=load(out/'pilot_matched_calendar.csv')
    assert len(matched)==90 and max(float(r['max_abs_start_change_min']) for r in matched)==0
    validation=load(out/'validation_summary.csv')
    assert sum(r['criterion_pass']=='True' for r in validation)>=2 and not any(r['criterion_pass']=='False' for r in validation)
    print('Audit passed: 1,700 original runs, 800 separate follow-up runs, 23,800 midnight records; all published level and paired CIs reproduced from per-replication CSVs.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,default=Path(__file__).resolve().parent/'results')
    audit(p.parse_args().out)
