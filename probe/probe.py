import json,urllib.request,time
H={'User-Agent':'Mozilla/5.0','Accept':'application/json'}
def get(u):
    t=time.time()
    try:
        r=urllib.request.urlopen(urllib.request.Request(u,headers=H),timeout=60); b=r.read()
        print('OK',r.status,len(b),round(time.time()-t,2),u); return b
    except Exception as e: print('ERR',u,e); return None
b=get('https://www.finnomena.com/fn3/api/fund/public/list')
if b:
    L=json.loads(b); print('n funds',len(L)); print(json.dumps(L[:2],ensure_ascii=False)[:800])
    by={f['short_code']:f for f in L}
    for code in ['SCBSEMI','TLWORLD-X','K-USXNDQ-A','SCBABS','KT-ARB-A','TNASDAQ-A','SCBS&P500']:
        f=by.get(code); print('--',code, f and f.get('id'))
        if f:
            nb=get(f"https://www.finnomena.com/fn3/api/fund/v2/public/funds/{f['id']}/nav/q?range=MAX")
            if nb:
                j=json.loads(nb); d=j.get('data',{}); n=d.get('navs',[])
                print(' keys',list(d.keys()),'navs',len(n), n[:2], n[-2:])
get('https://api.sec.or.th/')
get('https://www.finnomena.com/fn3/api/fund/public/filter/overview')
