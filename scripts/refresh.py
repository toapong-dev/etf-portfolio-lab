# Rebuilds the ETF Portfolio Lab dataset. Usage: python3 -I refresh.py <workdir>
# Writes <workdir>/out/etfs.json and <workdir>/out/d/<k>.json
import json,sys,subprocess,csv,io,math,os,bisect,datetime as dt
from concurrent.futures import ThreadPoolExecutor
WORK=sys.argv[1]; os.makedirs(WORK+'/lw',exist_ok=True)
META=WORK+'/funds_meta.json'; LW=WORK+'/lw'; OUT=WORK+'/raw.jsonl'
RAWGH='https://raw.githubusercontent.com'
def curl(url,dest): subprocess.run(['curl','-sSL','-m','120','--fail','-o',dest,url],check=True)
curl(f'{RAWGH}/alm0421/alm0421/HEAD/data/funds_meta.json',META)
for t in ['VT','QQQ','SMH','SGOV']:
    try: curl(f'{RAWGH}/a23882005/LivingWaterAI/HEAD/data/market_history/global/{t}.csv',f'{LW}/{t}.csv')
    except Exception as e: print('lw skip',t,e)
if os.path.exists(OUT): os.remove(OUT)
m=json.load(open(META))['funds']
etfs=sorted(k for k,v in m.items() if v.get('quote_type')=='ETF')
done=set()
if os.path.exists(OUT):
    for l in open(OUT):
        try: done.add(json.loads(l)['t'])
        except: pass
todo=[t for t in etfs if t not in done]
print('etfs',len(etfs),'todo',len(todo),flush=True)
def lwdivs(t):
    p=f'{LW}/{t}.csv'; d={}
    if os.path.exists(p):
        for r in csv.DictReader(open(p)):
            x=float(r['Dividends'] or 0)
            if x>0: d[r['Date']]=x
    return d
def work(t):
    for attempt in range(3):
        r=subprocess.run(['curl','-sSL','-m','60','--fail',f'https://raw.githubusercontent.com/alm0421/alm0421/HEAD/data/prices/{t}.csv'],capture_output=True)
        if r.returncode==0: break
    else: return {'t':t,'err':'download'}
    rows=list(csv.DictReader(io.StringIO(r.stdout.decode())))
    extra=lwdivs(t)
    dates=[];closes=[];divs=[]
    for x in rows:
        try: c=float(x['close'])
        except: continue
        if not (c>0) or math.isnan(c): continue
        dv=float(x.get('dividend') or 0) if (x.get('dividend') or '') not in ('','nan') else 0.0
        if dv==0 and x['date'] in extra: dv=extra[x['date']]
        dates.append(x['date']); closes.append(c); divs.append(dv)
    if len(dates)<2: return {'t':t,'err':'short'}
    # bad-tick filter: isolated spike that reverses next day
    flags=0
    for i in range(1,len(closes)-1):
        g1=closes[i]/closes[i-1]; g2=closes[i+1]/closes[i]
        if (g1>1.6 and g2<1/1.5) or (g1<1/1.6 and g2>1.5):
            closes[i]=closes[i-1]; flags+=1
    tr=[0.0]; L=0.0; big=0
    for i in range(1,len(closes)):
        g=(closes[i]+divs[i])/closes[i-1]
        if g>2.5 or g<0.4: big+=1
        L+=math.log(g); tr.append(L)
    return {'t':t,'d':dates,'L':[round(x*1e4) for x in tr],'px':closes[-1],'flags':flags,'big':big}
with open(OUT,'a') as f, ThreadPoolExecutor(24) as ex:
    for n,res in enumerate(ex.map(work,todo)):
        f.write(json.dumps(res,separators=(',',':'))+'\n')
        if n%250==0: print(n,res['t'],flush=True)
print('fetched',flush=True)

# ---- shard ----
RAW=OUT; OUTD=WORK+'/out'
import shutil; shutil.rmtree(OUTD,ignore_errors=True)
os.makedirs(OUTD+'/d',exist_ok=True)
meta=json.load(open(META))['funds']
recs={}
for l in open(RAW):
    r=json.loads(l)
    if 'err' in r: continue
    recs[r['t']]=r

# ---- proxies for non-US funds the archive does not carry ----
# VHYA (Vanguard FTSE All-World High Dividend Yield UCITS, USD Acc, LSE). Its index is the FTSE All-World HDY,
# which splits into the FTSE US HDY (VYM) and FTSE All-World ex-US HDY (VYMI). Blend at the fund's US weight,
# rebalanced monthly, minus the fee gap (VHYA 0.29% vs. the blend's ~0.13%).
PROXIES={'VHYA':{'legs':[('VYM',0.385),('VYMI',0.615)],'fee_gap':0.0016,
  'meta':{'name':'Vanguard FTSE All-World High Dividend Yield UCITS ETF (USD Acc) - proxy','category':'Global Equity Income','family':'Vanguard (UCITS, Ireland)','expense_ratio':0.0029,'net_assets':None,'yield':None,'inception':'2019-09-24'}}}
for pt,cfg in PROXIES.items():
    legs=[(recs.get(a),w) for a,w in cfg['legs']]
    if any(r is None for r,_ in legs): print('proxy skip',pt); continue
    maps=[dict(zip(r['d'],r['L'])) for r,_ in legs]
    common=sorted(set.intersection(*[set(m) for m in maps]))
    ws=[w for _,w in legs]; h=ws[:]; out=[0.0]; L=0.0; drag=cfg['fee_gap']/252
    for a,b in zip(common,common[1:]):
        h=[x*math.exp((m[b]-m[a])/1e4) for x,m in zip(h,maps)]; V=sum(h)
        L+=math.log(V)+math.log(1-drag); out.append(L); h=[x/V for x in h]
        if a[:7]!=b[:7]: h=ws[:]
    recs[pt]={'t':pt,'d':common,'L':[round(x*1e4) for x in out],'px':None,'big':0,'proxy':' + '.join(f"{int(w*1000)/10:g}% {a}" for a,w in cfg['legs'])}
    meta[pt]=cfg['meta']
    print('proxy',pt,common[0],common[-1],len(common))
# ---- manual series: funds with no public daily feed, from NAV CSVs TR exported (date,nav; accumulating, USD) ----
# Looked up next to this script (../data/manual), then in <workdir>/manual, then on the repo's main branch.
MANUAL={'FID-GTECH':{'name':'Fidelity Funds Global Technology Fund Y-Acc-USD','category':'Technology','family':'Fidelity (UCITS, Luxembourg)','isin':'LU1560650563','note':'Master of B-INNOTECH'},
        'CT-GTECH':{'name':'CT (Lux) Global Technology IU USD','category':'Technology','family':'Columbia Threadneedle (UCITS, Luxembourg)','isin':'LU0444972805','note':'Master of K-GTECH'}}
MDIRS=[os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','data','manual'),WORK+'/manual']
for mt,cfg in MANUAL.items():
    txt=None
    for d in MDIRS:
        p=os.path.join(d,mt+'.csv')
        if os.path.exists(p): txt=open(p).read(); break
    for ref in ([] if txt else ['HEAD','master-funds']):
        r=subprocess.run(['curl','-sSL','-m','60','--fail',f'{RAWGH}/toapong-dev/etf-portfolio-lab/{ref}/data/manual/{mt}.csv'],capture_output=True)
        if r.returncode==0: txt=r.stdout.decode(); break
    if txt is None: print('manual skip',mt); continue
    pts=[l.split(',') for l in txt.splitlines() if l[:1].isdigit()]
    pts=[(d[:10],float(v)) for d,v in pts if float(v)>0]
    if len(pts)<10: print('manual short',mt); continue
    L0=math.log(pts[0][1])
    recs[mt]={'t':mt,'d':[d for d,_ in pts],'L':[round((math.log(v)-L0)*1e4) for _,v in pts],'px':pts[-1][1],'big':0,'manual':True,'note':cfg['note']+' · '+cfg['isin']}
    meta[mt]={'name':cfg['name'],'category':cfg['category'],'family':cfg['family'],'expense_ratio':None,'net_assets':None,'yield':None,'inception':pts[0][0]}
    print('manual',mt,pts[0][0],pts[-1][0],len(pts))
spy=recs['SPY']; DATES=[d for d in spy['d'] if d>='1993-01-29']
# allow trailing dates beyond SPY's last if common
pos={d:i for i,d in enumerate(DATES)}
LAST=DATES[-1]
CUT=(dt.date.fromisoformat(LAST)-dt.timedelta(days=35)).isoformat()
def shift(d,months):
    y,m,dd=map(int,d.split('-')); m0=m-1+months; y+=m0//12; m0%=12
    import calendar; last=calendar.monthrange(y,m0+1)[1]; return f'{y:04d}-{m0+1:02d}-{min(dd,last):02d}'
def on_or_before(d): return bisect.bisect_right(DATES,d)-1
index=[]; series={}
skipped={'stale':0,'short':0}
for t,r in sorted(recs.items()):
    if r['d'][-1]<CUT and not r.get('manual'): skipped['stale']+=1; continue
    # map onto global axis with ffill
    dl=r['d']; L=r['L']; j=0; first=None; vals=[]
    s=bisect.bisect_left(DATES,dl[0]); e=on_or_before(dl[-1])
    if e-s<5: skipped['short']+=1; continue
    cur=None
    for i in range(s,e+1):
        d=DATES[i]
        while j<len(dl) and dl[j]<=d: cur=L[j]; j+=1
        if cur is None: cur=L[0]
        vals.append(cur)
    base=vals[0]; vals=[v-base for v in vals]
    series[t]=(s,e,vals)
    m=meta.get(t,{})
    def ret(months=None,ytd=False):
        ed=DATES[e]
        sd=f'{int(ed[:4])-1}-12-31' if ytd else shift(ed,-months)
        i0=on_or_before(sd)
        if i0<s: return None
        return round((math.exp((vals[e-s]-vals[i0-s])/1e4)-1)*1e4)/1e4
    a3=max(s,on_or_before(shift(DATES[e],-36)))
    rets=[(vals[i-s]-vals[i-1-s])/1e4 for i in range(a3+1,e+1)]
    vol=None
    if len(rets)>60:
        mu=sum(rets)/len(rets); vol=round(math.sqrt(sum((x-mu)**2 for x in rets)/(len(rets)-1)*252),4)
    pk=-1e18; dd=0
    for v in vals:
        pk=max(pk,v); dd=min(dd,v-pk)
    dd=round(math.exp(dd/1e4)-1,4)
    index.append({'t':t,'n':m.get('name') or t,'c':m.get('category') or '','f':m.get('family') or '',
        'er':m.get('expense_ratio'),'aum':m.get('net_assets'),'y':m.get('yield'),'inc':m.get('inception') or DATES[s],
        's':s,'e':e,'px':r['px'],'proxy':r.get('proxy'),'note':r.get('note'),
        'r':[ret(1),ret(3),ret(6),ret(ytd=True),ret(12),ret(36),ret(60),ret(120),ret(240)],'v':vol,'dd':dd,'flag':r.get('big',0)})
print('kept',len(index),'skipped',skipped)
# shards by size
shards=[];cur=[];size=0
for it in index:
    t=it['t']; s,e,vals=series[t]
    deltas=[vals[0]]+[vals[i]-vals[i-1] for i in range(1,len(vals))]
    txt=','.join(map(str,deltas))
    cur.append((t,s,txt)); size+=len(txt)
    if size>650_000: shards.append(cur); cur=[]; size=0
if cur: shards.append(cur)
for k,sh in enumerate(shards):
    obj={t:{'s':s,'d':txt} for t,s,txt in sh}
    json.dump(obj,open(f'{OUTD}/d/{k}.json','w'),separators=(',',':'))
    for t,_,_ in sh: next(i for i in index if i['t']==t)['k']=k
def r4(x): return None if x is None else float(f'{x:.4g}')
rows=[[i['t'],i['n'],i['c'],i['f'],r4(i['er']),r4(i['aum']),r4(i['y']),i['inc'],i['s'],i['e'],i['px'],i['k'],i['r'],i['v'],i['dd'],i['flag'],i.get('proxy'),i.get('note')] for i in index]
metaj=json.load(open(META))
json.dump({'asof':LAST,'built':dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%MZ'),'src_updated':metaj.get('updated_utc'),'dates':DATES,'cols':['t','n','c','f','er','aum','y','inc','s','e','px','k','r','v','dd','flag','proxy','note'],'etfs':rows},open(f'{OUTD}/etfs.json','w'),separators=(',',':'))
tot=sum(os.path.getsize(f'{OUTD}/d/{k}.json') for k in range(len(shards)))
print('shards',len(shards),'total MB',tot/1e6,'index MB',os.path.getsize(f'{OUTD}/etfs.json')/1e6)
