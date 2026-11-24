"""Export one arrival day of the common-input baseline for inspection.

Clocks are absolute minutes from the start of the simulated pilot-free main
replication, not times since midnight. Defaults to the first measurement day.
"""
from argparse import ArgumentParser
from pathlib import Path
import numpy as np
from engine import generate_inputs
from run_experiments import DAY, MAIN_SEED, OBS_DAYS, configs, save, simulate_env

def export(out,rep,measure_day):
    warm=7
    if not 1<=measure_day<=OBS_DAYS:raise ValueError('Use measurement day 1..14')
    runs,extra=simulate_env('B',MAIN_SEED,rep,warm*DAY,(warm+OBS_DAYS)*DAY,configs('B')[:3])
    inputs=generate_inputs('B',MAIN_SEED,rep,warm+OBS_DAYS+7+extra)
    day0=(warm+measure_day-1)*DAY
    results={p:r for _,p,_,_,r in runs}
    base=results['FCFS'];sample=[]
    for j in np.flatnonzero((base.arrival>=day0)&(base.arrival<day0+DAY)):
        idx=int(base.ids[j])
        row=dict(rep=rep,measure_day=measure_day,alert_id=idx,arrival_min=inputs.arrival[idx],
                 risk='HML'[int(inputs.risk[idx])],service_min=inputs.service[idx])
        for p,r in results.items():
            if r.ids[j]!=idx:raise ValueError('Input IDs not aligned')
            row[p+'_start_min']=r.start[j];row[p+'_finish_min']=r.finish[j]
        sample.append(row)
    save(out,sample)
    print(f'{len(sample)} common-input alert records: {out}')

if __name__=='__main__':
    p=ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,default=Path(__file__).resolve().parent/'results'/'example_alerts.csv')
    p.add_argument('--rep',type=int,default=0)
    p.add_argument('--day',type=int,default=1)
    args=p.parse_args();args.out.parent.mkdir(parents=True,exist_ok=True);export(args.out,args.rep,args.day)
