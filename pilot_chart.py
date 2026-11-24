"""Single-file offline SVG/HTML diagnostic, built from actual pilot daily means."""
from math import ceil
from html import escape

def draw(path, rows):
    colors={'FCFS':'#2367a0','STATIC':'#be4a24','DYNAMIC':'#008273'}
    parts=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Initialization diagnostic | Group 15</title><style>*{box-sizing:border-box}body{margin:0 auto;max-width:1200px;padding:40px 24px;background:#fbfaf6;color:#1e302e;font:16px/1.55 system-ui,sans-serif}h1{font-size:clamp(26px,4vw,40px);letter-spacing:-.045em;margin:.2em 0}h2{font-size:21px;margin-top:1.6em}p{max-width:78ch}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,290px),1fr));gap:12px}.chart{background:white;padding:12px}svg{width:100%;display:block}.tag{font-size:12px;letter-spacing:.12em;color:#526b63;font-weight:700}.key{margin:18px 0}.key b{margin-right:18px}.chart strong{font-size:15px}footer{font-size:13px;color:#526b63;margin-top:24px}</style><p class="tag">SEEM3410 / GROUP 15 / INITIALIZATION DIAGNOSTIC</p><h1>Does the empty start still matter?</h1><p>One point is the mean of 10 independent pilot replications. The warm-up sensitivity compares the same runs over days 8-21 and 15-28. Dashed vertical lines mark days 7 and 14. Midnight counts are snapshots, not daily average queue lengths.</p>']
    parts.append('<div class="key">'+''.join(f'<b style="color:{color}">&#9473; {p}</b>' for p,color in colors.items())+'</div>')
    for metric,title,scale in [('total_unfinished','Unfinished alerts at midnight (waiting + in service)',1),('H_completion_late','High-risk alerts finishing after 30 minutes (%)',100),('L_p95_wait_min','Low-risk 95th percentile of waiting time (min)',1)]:
        parts.append('<h2>'+escape(title)+'</h2><div class="grid">')
        largest=max(float(r[metric])*scale for r in rows); unit=5 if largest<100 else 25
        high=ceil(largest/unit)*unit
        X=lambda d:35+(d-1)*265/27
        Y=lambda val:145-123*val/high
        for env,name in [('B','B / Baseline'),('D','D / Demand +10%'),('R','R / High-risk mix 30%')]:
            parts.append(f'<section class="chart"><strong>{name}</strong><svg role="img" aria-label="{escape(title)}: {name}" viewBox="0 0 310 177">')
            for frac in (0,.5,1):
                y=Y(frac*high);parts.append(f'<path d="M35 {y}H300" stroke="#dbe2de"/><text x="29" y="{y+4}" text-anchor="end" font-size="10">{frac*high:g}</text>')
            for d in (1,7,14,21,28):
                x=X(d);parts.append(f'<text x="{x}" y="164" text-anchor="middle" font-size="10">{d}</text>')
                if d in (7,14):parts.append(f'<path d="M{x} 22V145" stroke="#b5c0b8" stroke-dasharray="3 3"/>')
            for p,col in colors.items():
                seq=sorted((r for r in rows if r['env']==env and r['policy']==p),key=lambda x:x['day'])
                assert len(seq)==28
                coords=' '.join(f'{X(r["day"]):.1f},{Y(float(r[metric])*scale):.1f}' for r in seq)
                parts.append(f'<polyline fill="none" stroke="{col}" stroke-width="1.6" points="{coords}"/>')
            parts.append('</svg></section>')
        parts.append('</div>')
    parts.append('<footer>Horizontal axis: elapsed day. Daily risk metrics use the arrival-day cohort, followed to completion. Within-replication p95 values use linear interpolation. Source: pilot_daily_means.csv; synthetic data. Quantitative warm-up tests: pilot_warmup_contrasts.csv.</footer></html>')
    path.write_text(''.join(parts),encoding='utf-8')
