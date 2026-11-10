"""Fetch Thai mutual fund data from the SEC Thailand Open API into a data folder.

Usage: SEC_API_KEY=... python3 -I sec_fetch.py <datadir> [--since 2016-01-01] [--budget-min 300]

Writes into <datadir>:
  profiles.json.gz      every fund class (proj_id, class, abbreviation, names, AMC, master fund, status)
  dividends.csv.gz      proj_id,class_abbr,book_close_date,dividend_date,value
  nav/YYYY-MM.csv.gz    proj_id,class,date,nav,net_asset   (one file per month)
  state.json            which months are complete

Completed months are never fetched again. The current and previous month are always re-fetched,
because AMCs revise late NAVs. Stops cleanly when the time budget runs out, so a long first backfill
can be spread over several runs.
"""
import os, sys, json, gzip, csv, io, time, threading, datetime as dt, urllib.request, urllib.parse, urllib.error
from collections import deque, Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

DATA = sys.argv[1]
ARGS = dict(zip(sys.argv[2::2], sys.argv[3::2]))
SINCE = ARGS.get('--since', '2016-01-01')
BUDGET = float(ARGS.get('--budget-min', '300')) * 60
KEY = os.environ.get('SEC_API_KEY', '').strip()
BASE = os.environ.get('SEC_API_BASE', 'https://api.sec.or.th').rstrip('/')
T0 = time.time()
if not KEY:
    print('SEC_API_KEY is not set; nothing fetched.'); sys.exit(0)
os.makedirs(DATA + '/nav', exist_ok=True)

class Limiter:  # SEC portal: at most 5000 calls per 300 s and >=16 ms between calls
    def __init__(s, calls=4000, period=300.0, gap=0.05):
        s.calls, s.period, s.gap, s.hits, s.last, s.lock = calls, period, gap, deque(), 0.0, threading.Lock()
    def wait(s):
        with s.lock:
            now = time.monotonic()
            while s.hits and now - s.hits[0] >= s.period: s.hits.popleft()
            if len(s.hits) >= s.calls:
                time.sleep(s.period - (now - s.hits[0]) + 0.01)
            g = s.gap - (time.monotonic() - s.last)
            if g > 0: time.sleep(g)
            s.last = time.monotonic(); s.hits.append(s.last)
LIM = Limiter(); CALLS = [0]; RETRIES = Counter()

def get(path, params):
    url = f'{BASE}{path}?{urllib.parse.urlencode(params)}'
    for attempt in range(8):
        LIM.wait(); CALLS[0] += 1
        req = urllib.request.Request(url, headers={'Ocp-Apim-Subscription-Key': KEY, 'Accept': 'application/json', 'Cache-Control': 'no-cache'})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                b = r.read()
                return json.loads(b) if b else {}
        except urllib.error.HTTPError as e:
            body = e.read()[:300].decode('utf8', 'replace')
            if e.code in (401, 403):
                sys.exit(f'SEC API refused the key for {path} (HTTP {e.code}): {body}. Check that the key is subscribed to this product.')
            if e.code == 404 or e.code == 204:
                return {}
            if e.code == 400 and params.get('start_nav_date') and params.get('start_nav_date') == params.get('end_nav_date') and not params.get('next_cursor'):
                return {}  # the NAV endpoint answers 400 for a market holiday with no NAV
            if e.code in (421, 429) or e.code >= 500:
                RETRIES[e.code] += 1
                if sum(RETRIES.values()) <= 5: print('retry', e.code, body[:120], flush=True)
                ra = e.headers.get('Retry-After'); time.sleep(float(ra) if ra and ra.isdigit() else min(60, 2 ** attempt)); continue
            raise RuntimeError(f'HTTP {e.code} {url}: {body}')
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            RETRIES[type(e).__name__] += 1
            if sum(RETRIES.values()) <= 5: print('retry', repr(e)[:120], flush=True)
            time.sleep(min(60, 2 ** attempt))
    raise RuntimeError(f'gave up on {url}')

def pages(path, params):
    cur = ''
    while True:
        p = dict(params, page_size=100)
        if cur: p['next_cursor'] = cur
        j = get(path, p)
        items = j.get('items') or j.get('data') or []
        yield from items
        cur = j.get('next_cursor') or ''
        if not cur or not items: return

def wgz(name, text):
    tmp = f'{DATA}/{name}.tmp'
    with gzip.open(tmp, 'wt', encoding='utf8', compresslevel=9) as f: f.write(text)
    os.replace(tmp, f'{DATA}/{name}')

# 1. profiles (fund list, classes, master funds): slow (~3 s a call), so refresh at most weekly
pp, state_p = f'{DATA}/profiles.json.gz', f'{DATA}/state.json'
state = json.load(open(state_p)) if os.path.exists(state_p) else {'complete': []}
# file times reset on checkout, so the fetch time lives in state.json
fresh = os.path.exists(pp) and time.time() - state.get('profiles_ts', 0) < 6 * 86400 and os.environ.get('SEC_FORCE_PROFILES') != '1'
prof = [] if fresh else list(pages('/v2/fund/general-info/profiles', {}))
keep = ['proj_id', 'proj_abbr_name', 'proj_name_en', 'proj_name_th', 'comp_name_en', 'unique_id', 'fund_status', 'regis_date', 'cancel_date',
        'management_style', 'feederfund_master_fund', 'invest_country_flag', 'fund_class_name', 'fund_class_tax_incentive_type', 'fund_class_isin_code']
if prof:
    state['profiles_ts'] = time.time()
    wgz('profiles.json.gz', json.dumps([{k: p.get(k) for k in keep} for p in prof], ensure_ascii=False, separators=(',', ':')))
print('profiles', len(prof) if prof else 'kept (fetched this week)', 'calls', CALLS[0], f'{int(time.time()-T0)}s', flush=True)

# 2. dividends. The unfiltered list only carries part of the history, so when profiles refresh (weekly)
#    each registered fund is asked for its own; on other days the unfiltered list is merged in for new payouts.
def drow(d): return (d.get('proj_id'), d.get('class_abbr_name'), (d.get('book_close_date') or '')[:10], (d.get('dividend_date') or '')[:10], str(d.get('dividend_value')))
dp = f'{DATA}/dividends.csv.gz'
have = set(tuple(r) for r in csv.reader(gzip.open(dp, 'rt', encoding='utf8'))) if os.path.exists(dp) else set()
dv = [drow(d) for d in pages('/v2/fund/daily-info/dividend-history', {})]
if prof or not state.get('div_full'):
    plist = prof or json.load(gzip.open(pp, 'rt', encoding='utf8'))
    pids = sorted({p['proj_id'] for p in plist if p.get('fund_status') in ('Registered', 'IPO', 'RG') and p.get('proj_id')})
    with ThreadPoolExecutor(12) as ex:
        for lst in ex.map(lambda pid: [drow(d) for d in pages('/v2/fund/daily-info/dividend-history', {'proj_id': pid})], pids): dv.extend(lst)
    state['div_full'] = time.time()
    print('dividend history asked per fund for', len(pids), 'funds', flush=True)
allrows = sorted(have | set(dv))
buf = io.StringIO(); w = csv.writer(buf); w.writerows(allrows)
wgz('dividends.csv.gz', buf.getvalue())
print('dividends', len(allrows), 'calls', CALLS[0], f'{int(time.time()-T0)}s', flush=True)
T1 = time.time()  # the time budget covers the NAV download

# 3. NAV by month
today = dt.date.today()
def months():
    y, m = map(int, SINCE[:7].split('-'))
    while (y, m) <= (today.year, today.month):
        yield f'{y:04d}-{m:02d}'; m += 1
        if m > 12: y, m = y + 1, 1
cur_m = today.strftime('%Y-%m'); prev_m = (today.replace(day=1) - dt.timedelta(days=1)).strftime('%Y-%m')
todo = [m for m in months() if m in (cur_m, prev_m) or m not in state['complete']]
todo.sort(key=lambda m: (m not in (cur_m, prev_m), m), reverse=False)  # refresh recent first, then backfill newest-to-oldest
todo = todo[:2] + sorted(todo[2:], reverse=True)
print('months to fetch', len(todo), flush=True)

def fetch_month(m):
    y, mm = map(int, m.split('-'))
    end = (dt.date(y + (mm == 12), mm % 12 + 1, 1) - dt.timedelta(days=1))
    # each day is its own cursor (~60 pages of 100), fetched in parallel: the API answers in ~1 s,
    # so parallel cursors are what lets the run approach the 5,000-calls-per-5-minutes limit
    def day(d):
        for attempt in range(3):  # a cursor that dies mid-way is restarted from the first page
            try: return day1(d)
            except RuntimeError as e:
                if attempt == 2: raise
                print(f'{d}: restarting after {str(e)[:80]}', flush=True); time.sleep(30)
    def day1(d):
        out = []
        for it in pages('/v2/fund/daily-info/nav', {'start_nav_date': d.isoformat(), 'end_nav_date': d.isoformat()}):
            if it.get('last_val') in (None, '', 0): continue
            out.append((it.get('proj_id'), it.get('fund_class_name') or 'main', (it.get('nav_date') or '')[:10], it.get('last_val'), it.get('net_asset')))
        return out
    days = [dt.date(y, mm, 1) + dt.timedelta(days=i) for i in range((end - dt.date(y, mm, 1)).days + 1)]
    days = [d for d in days if d.weekday() < 5 and d <= today]
    rows = []
    with ThreadPoolExecutor(4) as inner:
        for out in inner.map(day, days): rows.extend(out)
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    buf = io.StringIO(); w = csv.writer(buf); w.writerows(rows)
    wgz(f'nav/{m}.csv.gz', buf.getvalue())
    return m, len(rows)

done_now = 0
with ThreadPoolExecutor(4) as ex:
    futs = {}
    it = iter(todo)
    def submit_next():
        if time.time() - T1 > BUDGET: return False
        m = next(it, None)
        if m is None: return False
        futs[ex.submit(fetch_month, m)] = m; return True
    for _ in range(4): submit_next()
    while futs:
        for f in as_completed(list(futs)):
            m = futs.pop(f)
            try:
                m, n = f.result(); done_now += 1
                if m not in (cur_m, prev_m) and m not in state['complete']: state['complete'].append(m)
                print(f'{m}: {n} NAV rows · calls {CALLS[0]} · {int(time.time()-T0)}s', flush=True)
            except Exception as e:
                print(f'{m}: FAILED {e}', flush=True)
            json.dump(state, open(state_p, 'w'))
            submit_next()
            break
left = [m for m in months() if m not in state['complete'] and m not in (cur_m, prev_m)]
state['backfill_left'] = len(left); state['fetched_utc'] = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%MZ')
json.dump(state, open(state_p, 'w'))
print('retries', dict(RETRIES)); print('done', done_now, 'months this run;', len(left), 'months still to backfill; calls', CALLS[0], flush=True)
