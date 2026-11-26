"""Rebuild the precision intervals and paired differences from the archived cases."""
import argparse,csv
from collections import defaultdict
import numpy as np
import precision as p
import run_budget as b

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("--out",type=b.Path,default=b.HERE/"results");out=ap.parse_args().out
    def read(name):
        with (out/name).open(encoding="utf-8",newline="") as f:return list(csv.DictReader(f))
    rr=read("precision_replications.csv")
    assert len(rr)==p.N*6
    denom=defaultdict(set)
    for r in rr:
        denom[int(r["rep"])].add((r["H_n"],r["L_n"]))
        assert int(r["H_n"])>0 and int(r["L_n"])>0
        for short,long in (("H_late","H"),("L_long","L")):
            assert np.isclose(100*int(r[short+"_n"])/int(r[long+"_n"]),float(r[short+"_pct"]))
        assert float(r["paid_extra_h_day"])>=b.budget(r["window"])-1e-9
    assert set(denom)==set(range(p.N)) and all(len(s)==1 for s in denom.values())
    d={int(k):v for k,v in p.D["windows"].items()};lv,e=p.summarize(rr,d)
    for actual,expected in [(read("precision_levels.csv"),lv),(read("precision_paired.csv"),e)]:
        assert len(actual)==len(expected)
        for r,x in zip(actual,expected):
            for k in r:
                if isinstance(x[k],(float,int,np.number)) and not isinstance(x[k],bool):
                    assert np.isclose(float(r[k]),x[k],rtol=0,atol=1e-12),k
                else:assert str(x[k])==r[k],k
    print("Reviewed 7200 matched replays, case counts, levels, three-budget intervals and paired differences.")
if __name__=="__main__":main()
