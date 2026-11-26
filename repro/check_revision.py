"""Independent stored-result arithmetic and exact one-replication replay check."""
import argparse
import csv
import json
from math import fsum,isclose,sqrt,isfinite
from pathlib import Path
from statistics import stdev


def load(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))


def near(x,y):
    if not isclose(float(x),float(y),abs_tol=1e-9,rel_tol=1e-11):raise AssertionError((x,y))


def audit(out):
    design=json.loads((out/'frozen_design.json').read_text(encoding='utf-8'))
    manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
    raw=load(out/'replications.csv');scenarios=manifest['scenarios'];plans=design['plans'];n=design['replications']
    assert n==100
    expected={(s,p,r) for s in scenarios for p in plans for r in range(n)}
    ix={(r['scenario'],r['plan'],int(r['rep'])):r for r in raw}
    assert len(raw)==len(ix)==len(expected) and set(ix)==expected
    prob=['H_completion_late','L_wait_gt60','H_start_by15','L_wait_gt60_arrive_13_14','L_wait_gt60_arrive_21_22']
    for r in raw:
        for m in prob:assert 0<=float(r[m])<=1
        assert float(r['L_p95_wait_min'])>=0
        near(float(r['extra_scheduled_h_day'])+float(r['extra_overtime_h_day']),r['extra_paid_h_day'])
        near(72+float(r['extra_paid_h_day']),r['total_paid_h_day'])
        expected_scheduled=0 if r['plan']=='fixed3_A20' else 24 if r['plan']=='fixed4_A20' else 6
        near(r['extra_scheduled_h_day'],expected_scheduled)
        assert float(r['extra_overtime_h_day'])>=0
        for label in 'HML':
            assert int(r[label+'_n'])>0
            assert r[label+'_n']==ix[scenarios[0],plans[0],int(r['rep'])][label+'_n']
        for window in ('13_14','21_22'):
            assert int(r['L_arrive_'+window+'_n'])>0
            assert r['L_arrive_'+window+'_n']==ix[r['scenario'],plans[0],int(r['rep'])]['L_arrive_'+window+'_n']
    checked=0
    for name in ('levels','paired'):
        for row in load(out/f'{name}.csv'):
            scale=100 if row['unit'] in ('%','pp') else 1
            if name=='levels':values=[scale*float(ix[row['scenario'],row['plan'],r][row['metric']]) for r in range(n)]
            else:values=[scale*(float(ix[row['scenario'],row['alternative'],r][row['metric']])-float(ix[row['scenario'],row['reference'],r][row['metric']])) for r in range(n)]
            assert int(row['n_reps'])==n and all(isfinite(v) for v in values)
            avg=fsum(values)/n;h=1.9842169515864174*stdev(values)/sqrt(n)
            for k,v in [('estimate',avg),('ci_low',avg-h),('ci_high',avg+h),('halfwidth',h)]:near(row[k],v)
            checked+=1
    for row in load(out/'decisions.csv'):
        a=float(row['aggregate_L_upper_pct'])<=5
        w=max(float(row['original_close_13_upper_pct']),float(row['original_close_21_upper_pct']))<=5
        h=float(row['H_vs_same_schedule_FCFS_upper_pp'])<=-2
        for key,value in [('aggregate_pass',a),('fixed_windows_pass',w),('H_benefit_pass',h),('protected_candidate',a and w and h)]:
            assert row[key]==str(value)
    profiles={}
    for row in load(out/'input_profiles.csv'):profiles.setdefault(row['scenario'],[]).append(row)
    for scenario,rows in profiles.items():
        near(fsum((float(r['right_min'])-float(r['left_min']))*float(r['rate_per_hour'])/60 for r in rows),540)
    warm=load(out/'warmup_checks.csv') if (out/'warmup_checks.csv').exists() else []
    if warm:
        assert len(warm)==10*len(plans)*len(scenarios)
        changed=sum(int(r['differing_starts'])>0 for r in warm)
        maximum=max(float(r['max_abs_start_change_min']) for r in warm)
    else:changed=maximum=None
    # Replay code once against the effective frozen profiles, never against external files.
    from study import replicate
    profile_map={s:([float(rows[0]['left_min'])]+[float(r['right_min']) for r in rows],
                    [float(r['rate_per_hour']) for r in rows]) for s,rows in profiles.items()}
    replay=replicate((0,profile_map))
    for row in replay:
        old=ix[row['scenario'],row['plan'],0]
        for key,value in row.items():
            if isinstance(value,(int,float)):near(value,old[key])
            else:assert value==old[key]
    result=dict(archived_simulations=len(raw),independently_recomputed_intervals=checked,replayed_configurations=len(replay),
                warmup_comparisons=len(warm),warmup_comparisons_with_changed_starts=changed,max_warmup_change_min=maximum)
    print(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=Path(__file__).resolve().parent/'results')
    audit(p.parse_args().out)
