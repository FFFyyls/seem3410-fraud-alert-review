"""Audit the reproducibility tables using input numerators/denominators and paired keys."""
from pathlib import Path
from statistics import mean,stdev
from math import sqrt,isclose
import csv,sys,json

def check(folder):
    def rows(name):
        with (folder/name).open(newline='') as f:return list(csv.DictReader(f))
    def eq(a,b): assert isclose(float(a),float(b),rel_tol=1e-12,abs_tol=1e-10),(a,b)
    for prefix,n,k in [('screening',32,25),('holdout',80,5),('finalist',80,2)]:
        raw=rows(prefix+'_reps.csv');lookup={(r['plan'],int(r['rep'])):r for r in raw}
        assert len(raw)==len(lookup)==n*k
        for r in raw:
            eq(r['H_late_pct'],100*int(r['H_late_n'])/int(r['H_n']))
            eq(r['L_long_pct'],100*int(r['L_long_n'])/int(r['L_n']))
            assert float(r['paid_h_day'])>=6
        for i in range(n):
            same_rep=[r for (plan,j),r in lookup.items() if j==i]
            assert len({(r['H_n'],r['L_n']) for r in same_rep})==1
        level=rows('screening.csv' if prefix=='screening' else prefix+'_levels.csv')
        for r in level:
            for metric in ['H_late_pct','L_long_pct','paid_h_day','L_13_14_pct','L_21_22_pct']:
                vals=[float(lookup[r['plan'],i][metric]) for i in range(n)]
                center=mean(vals);half={32:2.0395134464,80:1.9904502102}[n]*stdev(vals)/sqrt(n)
                eq(center,r[metric]);eq(center-half,r[metric+'_lo']);eq(center+half,r[metric+'_hi'])
        if prefix=='screening':continue
        for r in rows(prefix+'_paired.csv'):
            diffs=[float(lookup[r['alternative'],i][r['metric']])-float(lookup[r['reference'],i][r['metric']]) for i in range(n)]
            center=mean(diffs);half=1.9904502102*stdev(diffs)/sqrt(n)
            eq(center,r['estimate']);eq(center-half,r['ci_low']);eq(center+half,r['ci_high'])
    lock=json.loads((folder/'selection.json').read_text())
    allowed=sorted((r for r in rows('screening.csv') if float(r['L_long_pct_hi'])<=5),key=lambda r:float(r['H_late_pct']))
    assert len(allowed)==lock['screened_in']
    assert (int(allowed[0]['lunch_offset']),int(allowed[0]['evening_offset']))==(lock['selected_lunch_offset_min'],lock['selected_evening_offset_min'])
    print('All screening, holdout and finalist rates, intervals and paired comparisons agree.')

if __name__=='__main__':check(Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parent/'results')
