"""Build the Thai fund dataset for the page from the SEC data folder.

Usage: python3 -I build.py <datadir> <outdir> [categories.csv]
Writes <outdir>/etfs.json (index) and <outdir>/d/<k>.json (shards), same format as the US ETF page.
"""
import os, sys, json, gzip, csv, math, bisect, glob, datetime as dt, calendar
from collections import defaultdict, Counter

DATA, OUTD = sys.argv[1], sys.argv[2]
CATS = sys.argv[3] if len(sys.argv) > 3 else None
os.makedirs(OUTD + '/d', exist_ok=True)
for f in glob.glob(OUTD + '/d/*.json'): os.remove(f)

def rgz(p): return gzip.open(p, 'rt', encoding='utf8')

# ---- fund classes ----
prof = json.load(rgz(f'{DATA}/profiles.json.gz'))
classes = defaultdict(list)  # proj_id -> class rows
for p in prof: classes[p['proj_id']].append(p)
def code_of(p):
    c = (p.get('fund_class_name') or '').strip()
    return c if c and c.lower() != 'main' else (p.get('proj_abbr_name') or '').strip()
key2code, meta = {}, {}
for pid, rows in classes.items():
    for p in rows:
        code = code_of(p)
        if not code: continue
        k = (pid, (p.get('fund_class_name') or 'main').strip() or 'main')
        key2code[k] = code
        if len(rows) == 1: key2code[(pid, 'main')] = code
        # prefer an active record when a code appears more than once
        old = meta.get(code)
        if old is None or (old['status'] not in ('Registered', 'IPO') and p.get('fund_status') in ('Registered', 'IPO')):
            meta[code] = {'pid': pid, 'name': p.get('proj_name_en') or p.get('proj_name_th') or code, 'name_th': p.get('proj_name_th'),
                          'amc': p.get('comp_name_en') or p.get('unique_id') or '', 'master': p.get('feederfund_master_fund'),
                          'status': p.get('fund_status'), 'regis': p.get('regis_date'), 'tax': p.get('fund_class_tax_incentive_type'),
                          'style': p.get('management_style')}

# ---- optional categories from the fund database (sheet 1 columns only) ----
cat = {}
if CATS and os.path.exists(CATS):
    for r in csv.DictReader(open(CATS, encoding='utf8')): cat[r['code']] = r
print('profiles', len(prof), 'codes', len(meta), 'categorised', len(cat))

# ---- NAV ----
nav = defaultdict(dict); aum = {}
for f in sorted(glob.glob(f'{DATA}/nav/*.csv.gz')):
    for pid, cls, d, v, na in csv.reader(rgz(f)):
        d = (d or '')[:10]
        code = key2code.get((pid, cls)) or key2code.get((pid, 'main'))
        if not code: continue
        try: v = float(v)
        except ValueError: continue
        if v > 0: nav[code][d] = v
        if na not in ('', 'None'):
            try:
                if code not in aum or d >= aum[code][0]: aum[code] = (d, float(na))
            except ValueError: pass
print('codes with NAV', len(nav))

# ---- dividends (per unit, THB), keyed by class abbreviation ----
divs = defaultdict(list)
if os.path.exists(f'{DATA}/dividends.csv.gz'):
    for pid, abbr, bcd, pay, val in csv.reader(rgz(f'{DATA}/dividends.csv.gz')):
        try: val = float(val)
        except ValueError: continue
        code = abbr if abbr in nav else key2code.get((pid, 'main'))
        if code and bcd and val > 0: divs[code].append((bcd[:10], val))

# ---- global date axis: Thai business days (dates on which a good share of funds report) ----
cnt = Counter(d for s in nav.values() for d in s)
by_month = defaultdict(int)
for d, n in cnt.items(): by_month[d[:7]] = max(by_month[d[:7]], n)
DATES = sorted(d for d, n in cnt.items() if n >= 0.3 * by_month[d[:7]] and dt.date.fromisoformat(d).weekday() < 5)
LAST = DATES[-1]
w0 = max(dt.date.fromisoformat(DATES[0]), dt.date.fromisoformat(LAST) - dt.timedelta(days=3 * 365))
span = (dt.date.fromisoformat(LAST) - w0).days / 365.25
PPY = round(sum(1 for d in DATES if d > w0.isoformat()) / span) if span > 0.25 else 243  # NAV days per year, ~243 for Thailand
CUT = (dt.date.fromisoformat(LAST) - dt.timedelta(days=35)).isoformat()
def shift(d, months):
    y, m, dd = map(int, d.split('-')); m0 = m - 1 + months; y += m0 // 12; m0 %= 12
    return f'{y:04d}-{m0+1:02d}-{min(dd, calendar.monthrange(y, m0 + 1)[1]):02d}'
def on_or_before(d): return bisect.bisect_right(DATES, d) - 1

def total_return(code):
    s = nav[code]; dl = sorted(s); px = [s[d] for d in dl]
    flags = 0
    for i in range(1, len(px) - 1):  # isolated bad prints that reverse the next day
        g1, g2 = px[i] / px[i - 1], px[i + 1] / px[i]
        if (g1 > 1.6 and g2 < 1 / 1.5) or (g1 < 1 / 1.6 and g2 > 1.5) or (abs(g1 - 1) > 0.15 and abs(g1 * g2 - 1) < 0.01): px[i] = px[i - 1]; flags += 1
    add = [0.0] * len(dl)
    for bcd, v in divs.get(code, []):
        # NAV drops on the XD day, which sits at or just before the book-close date: take the weakest day in the window
        lo = bisect.bisect_left(dl, (dt.date.fromisoformat(bcd) - dt.timedelta(days=5)).isoformat())
        hi = bisect.bisect_right(dl, (dt.date.fromisoformat(bcd) + dt.timedelta(days=3)).isoformat())
        cand = [i for i in range(max(lo, 1), min(hi, len(dl)))]
        if not cand: continue
        i = min(cand, key=lambda i: px[i] / px[i - 1]); add[i] += v
    L, out, big = 0.0, [0.0], 0
    for i in range(1, len(px)):
        g = (px[i] + add[i]) / px[i - 1]
        if g > 2.5 or g < 0.4: big += 1
        L += math.log(g); out.append(L)
    return dl, [round(x * 1e4) for x in out], px[-1], big

index, series, skipped = [], {}, Counter()
for code in sorted(nav):
    if len(nav[code]) < 6: skipped['short'] += 1; continue
    dl, L, px, big = total_return(code)
    if dl[-1] < CUT: skipped['stale'] += 1; continue
    s = bisect.bisect_left(DATES, dl[0]); e = on_or_before(dl[-1])
    if e - s < 5: skipped['short'] += 1; continue
    vals, j, cur = [], 0, None
    for i in range(s, e + 1):
        d = DATES[i]
        while j < len(dl) and dl[j] <= d: cur = L[j]; j += 1
        vals.append(L[0] if cur is None else cur)
    base = vals[0]; vals = [v - base for v in vals]
    series[code] = (s, e, vals)
    def ret(months=None, ytd=False):
        ed = DATES[e]; sd = f'{int(ed[:4])-1}-12-31' if ytd else shift(ed, -months)
        i0 = on_or_before(sd)
        if i0 < s: return None
        return round((math.exp((vals[e - s] - vals[i0 - s]) / 1e4) - 1) * 1e4) / 1e4
    a3 = max(s, on_or_before(shift(DATES[e], -36)))
    rets = [(vals[i - s] - vals[i - 1 - s]) / 1e4 for i in range(a3 + 1, e + 1)]
    vol = None
    if len(rets) > 60:
        mu = sum(rets) / len(rets); vol = round(math.sqrt(sum((x - mu) ** 2 for x in rets) / (len(rets) - 1) * PPY), 4)
    pk, dd = -1e18, 0
    for v in vals: pk = max(pk, v); dd = min(dd, v - pk)
    m, c = meta.get(code, {}), cat.get(code, {})
    index.append({'t': code, 'n': m.get('name') or code, 'c': c.get('category') or '', 'f': c.get('amc') or m.get('amc') or '',
        'er': None, 'aum': aum.get(code, (0, None))[1], 'y': None, 'inc': (m.get('regis') or DATES[s])[:10], 's': s, 'e': e, 'px': px, 'proxy': None,
        'r': [ret(1), ret(3), ret(6), ret(ytd=True), ret(12), ret(36), ret(60), ret(120), ret(240)], 'v': vol, 'dd': round(math.exp(dd / 1e4) - 1, 4), 'flag': big,
        'mf': c.get('master') or m.get('master') or None, 'ft': c.get('type') or m.get('tax') or None, 'st': c.get('style') or None, 'dv': c.get('dividend') or None, 'th': m.get('name_th')})
print('kept', len(index), 'skipped', dict(skipped))

# cash proxy for "Optionality" and the risk-free rate: the largest Thai money-market fund with 3+ years of history
mm = [i for i in index if ('Money Market' in i['c'] or 'MONEY MARKET' in (i['n'] or '').upper()) and (i['ft'] in (None, '', 'General'))]
mm3 = [i for i in mm if i['r'][5] is not None] or mm
CASH = max(mm3, key=lambda i: i['aum'] or 0)['t'] if mm3 else None
print('cash fund', CASH)

shards, cur, size = [], [], 0
for it in index:
    s, e, vals = series[it['t']]
    txt = ','.join(map(str, [vals[0]] + [vals[i] - vals[i - 1] for i in range(1, len(vals))]))
    cur.append((it['t'], s, txt)); size += len(txt)
    if size > 650_000: shards.append(cur); cur, size = [], 0
if cur: shards.append(cur)
pos = {it['t']: it for it in index}
for k, sh in enumerate(shards):
    json.dump({t: {'s': s, 'd': txt} for t, s, txt in sh}, open(f'{OUTD}/d/{k}.json', 'w'), separators=(',', ':'))
    for t, _, _ in sh: pos[t]['k'] = k
def r4(x): return None if x is None else float(f'{x:.4g}')
cols = ['t', 'n', 'c', 'f', 'er', 'aum', 'y', 'inc', 's', 'e', 'px', 'k', 'r', 'v', 'dd', 'flag', 'proxy', 'mf', 'ft', 'st', 'dv', 'th']
rows = [[i['t'], i['n'], i['c'], i['f'], None, r4(i['aum']), None, i['inc'], i['s'], i['e'], i['px'], i['k'], i['r'], i['v'], i['dd'], i['flag'], None,
         i['mf'], i['ft'], i['st'], i['dv'], i['th']] for i in index]
st = json.load(open(f'{DATA}/state.json')) if os.path.exists(f'{DATA}/state.json') else {}
json.dump({'asof': LAST, 'built': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%MZ'), 'src_updated': st.get('fetched_utc'),
           'backfill_left': st.get('backfill_left'), 'ppy': PPY, 'cash': CASH, 'dates': DATES, 'cols': cols, 'etfs': rows},
          open(f'{OUTD}/etfs.json', 'w', encoding='utf8'), ensure_ascii=False, separators=(',', ':'))
print('shards', len(shards), 'MB', sum(os.path.getsize(f'{OUTD}/d/{k}.json') for k in range(len(shards))) / 1e6, 'asof', LAST, 'ppy', PPY)
