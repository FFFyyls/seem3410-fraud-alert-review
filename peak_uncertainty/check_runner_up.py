"""Independent secondary contrast for close screening finalists; does not reselect."""
import argparse,csv,json
from pathlib import Path
import experiment as e

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,default=e.HERE/'results');p.add_argument('--workers',type=int,default=4);a=p.parse_args()
    with (a.out/'screening.csv').open(newline='') as f:
        candidates=[r for r in csv.DictReader(f) if float(r['L_long_pct_hi'])<=5.]
    if len(candidates)<2:raise ValueError('fewer than two eligible finalists')
    order=sorted(candidates,key=lambda r:(float(r['H_late_pct']),float(r['L_long_pct']),abs(int(r['lunch_offset']))+abs(int(r['evening_offset'])),int(r['lunch_offset']),int(r['evening_offset'])))
    plans=[(int(r['lunch_offset']),int(r['evening_offset']),'A20','uncertain') for r in order[:2]]
    locked=json.loads((a.out/'selection.json').read_text())
    assert plans[0][:2]==(locked['selected_lunch_offset_min'],locked['selected_evening_offset_min'])
    rows=e.execute(34102613,80,plans,a.workers)
    e.save(a.out/'finalist_reps.csv',rows);e.save(a.out/'finalist_levels.csv',e.levels(rows))
    e.save(a.out/'finalist_paired.csv',e.pair(rows,[('near_runner_up_minus_locked',e.label(*plans[1]),e.label(*plans[0]))]))
if __name__=='__main__':main()
