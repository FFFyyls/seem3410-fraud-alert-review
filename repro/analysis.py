"""Replication-level DES estimands, pointwise Student intervals and decision rules."""
import math
import numpy as np

# Two-sided 95% Student critical values for n=2..100 independent units.
# Invert I_{df/(df+t^2)}(df/2,1/2)=.05 at df=n-1; no SciPy dependency.
T975 = (None,None,
    12.706204736174705,4.302652729749464,3.1824463052837095,2.7764451051977943,
    2.5705818356363155,2.44691185114497,2.3646242515927853,2.3060041352041667,
    2.2621571627982053,2.228138851986275,2.2009851600916397,2.178812829667229,
    2.1603686564627926,2.144786687917804,2.1314495455597755,2.1199052992212546,
    2.109815577833317,2.1009220402410387,2.0930240544083096,2.085963447265865,
    2.0796138447276804,2.0738730679040263,2.0686576104190486,2.063898561628026,
    2.0595385527532977,2.055529438642873,2.0518305164802855,2.048407141795245,
    2.0452296421327043,2.042272456301238,2.0395134463964086,2.036933343460102,
    2.034515297449339,2.032244509317719,2.0301079282503434,2.028094000980451,
    2.0261924630291097,2.02439416391197,2.0226909200367613,2.0210753903062733,
    2.019540970441376,2.018081702818445,2.0166921992278244,2.0153675744437636,
    2.0141033888808466,2.012895598919429,2.011740513729766,2.0106347576242323,
    2.0095752371292397,2.008559112100761,2.007583770315836,2.0066468050616884,
    2.005745995317869,2.004879288188057,2.004044783289146,2.0032407188478722,
    2.0024654592910074,2.001717484145236,2.000995378088268,2.0002978220142604,
    1.9996235849949398,1.9989715170333788,1.9983405425207414,1.997729654317693,
    1.997137908392004,1.996564418952312,1.9960083540252966,1.995468931429844,
    1.9949454151072379,1.9944371117711865,1.9939433678456258,1.9934635666618723,
    1.9929971258898551,1.9925434951809327,1.992102154002242,1.9916726096446644,
    1.991254395388385,1.9908470688116908,1.990450210230129,1.9900634212544461,
    1.9896863234569029,1.9893185571365726,1.9889597801751628,1.9886096669757092,
    1.988267907477222,1.9879342062390206,1.9876082815890712,1.9872898648311697,
    1.9869786995062815,1.9866745407037683,1.9863771544186182,1.9860863169511302,
    1.9858018143458234,1.9855234418666043,1.9852510035054982,1.9849843115224575,
    1.9847231860139847,1.9844674545084817,1.9842169515864174,
)
SLA = (30.,60.,120.)
KEY = ('H_completion_late','L_wait_gt60','L_p95_wait_min')

def class_metrics(risk, wait, duration):
    out = {}
    for i,label in enumerate('HML'):
        ix = (risk==i)
        w, t = wait[ix], duration[ix]
        if not len(w):
            out[label+'_n']=0
            for suffix in ('mean_wait_min','p95_wait_min','mean_completion_min',
                           'p95_completion_min','completion_ontime','completion_late'):
                out[label+'_'+suffix]=float('nan')
            if i==0: out['H_start_by15']=float('nan')
            if i==2: out['L_wait_gt60']=float('nan')
            continue
        late = float(np.mean(t>SLA[i]))
        out.update({label+'_n':len(w),label+'_mean_wait_min':float(np.mean(w)),
                    label+'_p95_wait_min':float(np.quantile(w,.95,method='linear')),
                    label+'_mean_completion_min':float(np.mean(t)),
                    label+'_p95_completion_min':float(np.quantile(t,.95,method='linear')),
                    label+'_completion_ontime':1.-late,label+'_completion_late':late})
        if i==0: out['H_start_by15'] = float(np.mean(w<=15))
        if i==2: out['L_wait_gt60'] = float(np.mean(w>60))
    return out

def summarize(r):
    out = class_metrics(r.risk,r.start-r.arrival,r.finish-r.arrival)
    out.update({'mean_queue':r.mean_queue,'utilization':r.utilization,
                'max_queue':r.max_queue,'end_queue':r.backlog_at_end,
                'unfinished_cohort_at_end':r.unfinished_at_end})
    return out

def mean_ci(values):
    a = np.array(values,dtype=float)
    if np.isinf(a).any(): raise ValueError('Infinite metric')
    a=a[~np.isnan(a)]; n=len(a)
    if n>100:raise ValueError('R exceeds prespecified cap of 100')
    if n<2:
        result=dict.fromkeys(('estimate','ci_low','ci_high','halfwidth','sd','se'),float('nan'))
        if n==1: result['estimate']=float(a[0])
        return dict(n_reps=n,**result)
    mu,sd = float(np.mean(a)),float(np.std(a,ddof=1))
    se = sd/math.sqrt(n)
    h = T975[n]*se
    return dict(n_reps=n,estimate=mu,ci_low=mu-h,ci_high=mu+h,halfwidth=h,sd=sd,se=se)

def display_scale(metric,difference=False):
    if (metric.endswith(('_ontime','_late')) or metric in ('H_start_by15','L_wait_gt60','utilization')):
        return 100.,('pp' if difference else '%')
    if metric.endswith('_min'): return 1.,'min'
    return 1.,'alerts'

def paired(alt,base,metric):
    a={r['rep']:r[metric] for r in alt}; b={r['rep']:r[metric] for r in base}
    if not a or a.keys()!=b.keys() or len(a)!=len(alt) or len(b)!=len(base):
        raise ValueError('Missing, duplicate or mismatched replication IDs')
    scale,unit=display_scale(metric,True)
    return dict(metric=metric,unit=unit,**mean_ci([(a[k]-b[k])*scale for k in sorted(a)]))

def decide_warmup(rows):
    return 14 if any(abs(x['estimate'])>({'H_completion_late':1.,'L_p95_wait_min':2.}[x['metric']])
                     and (x['ci_low']>0 or x['ci_high']<0) for x in rows) else 7

def decide_replications(required):
    return min(100,max(40,10*math.ceil(max(required)/10)))

def guardrail(lower_pct,upper_pct):
    return 'meets' if upper_pct<=5. else ('exceeds' if lower_pct>5. else 'uncertain')
