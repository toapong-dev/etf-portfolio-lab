"""Make the Thai fund page from the US ETF page, so both share one codebase.
Usage: python3 -I make_page.py <index.html> <out.html>. Fails loudly if the source page changed shape."""
import re, sys
src = open(sys.argv[1], encoding='utf8').read()
def R(old, new, count=1):
    global src
    n = src.count(old)
    if n < 1 or (count and n != count): sys.exit(f'make_page: expected {count or ">=1"} of {old[:70]!r}, found {n}')
    src = src.replace(old, new)

R('<title>ETF Portfolio Lab</title>', '<title>Thai Fund Portfolio Lab</title>')
R('<h1 id="title">Portfolio vs. ETFs</h1>', '<h1 id="title">Portfolio vs. Thai funds</h1>')
R('Pick any of the <span id="etfCount">5,700+</span> US-listed ETFs, set weights,', 'Pick any of the <span id="etfCount">4,000+</span> Thai mutual funds (all classes, including RMF, SSF and Thai ESG), set weights,')
R('Loading ETF data…', 'Loading Thai fund data…')
R('placeholder="Add any US ETF by ticker or name"', 'placeholder="Add a Thai fund by code, name or master fund"')
R('aria-label="Add an ETF"', 'aria-label="Add a fund"')
R('<option value="BIL">T-bill rate (BIL)</option>', '<option value="BIL">Money market fund rate</option>')
R('Show Thai feeder fund codes', 'Show master fund for feeder funds')
R('browse all ETFs in the table further down', 'browse all Thai funds in the table further down')
R('<h2 id="h-scr">All US ETFs</h2>', '<h2 id="h-scr">All Thai funds</h2>')
R('Every US-listed ETF in the dataset.', 'Every Thai mutual fund class with a NAV in the last 35 days.')
R('placeholder="Ticker or name, e.g. dividend, gold, IVV"', 'placeholder="Code, name or master fund, e.g. TLWORLD, gold, Vanguard"')
R('<option value="1e8" selected>Over $100M</option><option value="1e9">Over $1B</option><option value="1e10">Over $10B</option>',
  '<option value="1e8" selected>Over ฿100M</option><option value="1e9">Over ฿1B</option><option value="1e10">Over ฿10B</option>')
R('<input type="checkbox" id="scrLev" checked> Hide leveraged and inverse', '<input type="checkbox" id="scrLev" checked> Hide fixed-term and triggered funds')
R('Keep T-bill funds (SGOV, BIL, SHV) at their current weight', 'Keep money market funds and TLUSGOV at their current weight')
# footer
src = re.sub(r'<p class="foot">Data: daily closes.*?</p>', '<p class="foot">Data: daily NAV and dividend history from the SEC Thailand Open API (api.sec.or.th), back to 2016. Total return reinvests each dividend on the day the NAV goes ex-dividend. Categories, style, fund type and master funds come from the AVP fund database (30 Sep 2026); AMC names and fund status from the SEC. Returns are in Thai baht after each fund\'s fees. Unhedged (UH) and hedged (H) classes differ by currency effect. Very new funds and closed fixed-term funds have short histories. A GitHub workflow rebuilds the data Tue–Sat at 10:47 Bangkok time. Not investment advice: optimizer results are fit to past data and change with the lookback.</p>', src, count=1, flags=re.S)
# JS data hooks
R("const THAI = {VT:'TLWORLD-X', QQQ:'TLUSNDQ-H · TNASDAQ', SMH:'TLSEMICON · SCBSEMI (UCITS twin)', XLV:'TUSHEALTH-A', SCHD:'TLUSHD-H', SGOV:'TLUSGOV', VDC:null};",
  "let CASHT='KKP CASH', PPY=__PPY__; const isCashLike=t=>t===CASHT||t==='TLUSGOV'||/Money Market/.test((D.meta[t]||{}).c||'');")
R("const EXAMPLE = {holdings:[['VT',40],['QQQ',5],['SMH',5],['VDC',10],['XLV',10],['SCHD',10],['SGOV',15]], opt:5};",
  "const EXAMPLE = {holdings:[['B-INNOTECHRMF',20],['K-GTECH',20],['MM-RMF',30],['B-CHINAARMF',20],['BGOLD',10]], opt:0};")
R("DATES=j.dates; N=DATES.length;", "DATES=j.dates; N=DATES.length; if(j.cash) CASHT=j.cash; if(j.ppy) PPY=j.ppy; D.backfill=j.backfill_left;")
R("localStorage.getItem('etfLab.v1')", "localStorage.getItem('thaiLab.v1')")
R("localStorage.setItem('etfLab.v1'", "localStorage.setItem('thaiLab.v1'")
R("S.cash==='BIL' ? 'BIL' : 'CASH'", "S.cash==='BIL' ? CASHT : 'CASH'")
R("'earns T-bill rate'", "'earns '+CASHT+' (money market)'")
R("seriesOf('BIL')", "seriesOf(CASHT)")
R(",'BIL']", ",CASHT]", count=0)
R("rng('BIL')", "rng(CASHT)")
R("vs T-bill ${pct(rf,1,false)}", "vs money market ${pct(rf,1,false)}")
R("filter(t=>!(fixOn && ['SGOV','BIL','SHV'].includes(t)))", "filter(t=>!(fixOn && isCashLike(t)))")
R("const CASHLIKE=['SGOV','BIL','SHV'];", "")
R("fixOn && CASHLIKE.includes(t)", "fixOn && isCashLike(t)")
R("non-T-bill funds to optimize, or untick the T-bill option.", "funds other than money market funds to optimize, or untick the money market option.")
R("function thaiLine(t){ if(!S.thai) return ''; if(t in THAI){ return THAI[t] ? `<span class=\"thai\">${THAI[t]}</span>` : `<span class=\"thai none\">No Thai feeder found</span>`; } return ''; }",
  "function thaiLine(t){ const m=D.meta[t]; if(!S.thai||!m) return ''; const bits=[m.mf&&!/^ลงทุนเองโดยตรง/.test(m.mf)?'Master: '+m.mf:'', m.ft&&m.ft!=='General'?m.ft:''].filter(Boolean); return bits.length?`<span class=\"thai\">${bits.join(' · ')}</span>`:''; }")
src = re.sub(r'(?<![\w.])252(?![\w.])', 'PPY', src).replace('__PPY__', '252')
# money formatting: baht
R("const fmtAum = x => x==null ? '–' : x>=1e9 ? '$'+(x/1e9).toFixed(x>=1e10?0:1)+'B' : x>=1e6 ? '$'+(x/1e6).toFixed(0)+'M' : '$'+(x/1e3).toFixed(0)+'K';",
  "const fmtAum = x => x==null ? '–' : x>=1e9 ? '฿'+(x/1e9).toFixed(x>=1e10?0:1)+'B' : x>=1e6 ? '฿'+(x/1e6).toFixed(0)+'M' : '฿'+(x/1e3).toFixed(0)+'K';")
R("'$'+D.t[k].px.toFixed(2)", "D.t[k].px.toFixed(4)")
R("'Pick some ETFs'", "'Pick some funds'")
R("toast(`No US ETF matches \"${t}\".`)", "toast(`No Thai fund matches \"${t}\".`)")
# search also matches master fund and Thai name
R("else if(q.length>1 && (m.n||'').toUpperCase().includes(q)) b.push(m);",
  "else if(q.length>1 && ((m.n||'')+' '+(m.mf||'')+' '+(m.th||'')).toUpperCase().includes(q)) b.push(m);")
R("if(q && !(m.t.startsWith(q) || (m.n||'').toUpperCase().includes(q))) return false;",
  "if(q && !(m.t.startsWith(q) || ((m.n||'')+' '+(m.mf||'')+' '+(m.th||'')).toUpperCase().includes(q))) return false;")
R("if(hideLev && /^Trading--/.test(m.c||'')) return false;", "if(hideLev && /Fixed Term|Triggered|Capital Protected/.test(m.c||'')) return false;")
# screener columns: AMC and fund type instead of expense and yield
R("['er','Expense',x=>x==null?'–':(x*100).toFixed(2)+'%','asc']", "['f','AMC',x=>x||'–','asc'],['ft','Type',x=>x||'–','asc']")
R("['y','Yield',x=>x==null?'–':(x*100).toFixed(2)+'%','desc'],", "")
R("matching ETFs (", "matching funds (")
R("Returns are total return to each fund's latest close.", "Returns are total return to each fund's latest NAV, in baht.")
# freshness
R("${D.list.length.toLocaleString('en-US')} US ETFs · prices through ${fmtDate(ASOF)}", "${D.list.length.toLocaleString('en-US')} Thai funds · NAV through ${fmtDate(ASOF)}")
R("from a Yahoo Finance mirror updated ${fmtDT(D.src)}. Refreshes automatically Tue–Sat at 10:47 Bangkok time, after each US trading day.",
  "from the SEC Thailand Open API (fetched ${fmtDT(D.src)}). Refreshes automatically Tue–Sat at 10:47 Bangkok time.${D.backfill?` History still loading: ${D.backfill} months to go.`:''}")
R("Date.parse(ASOF+'T21:00:00Z')", "Date.parse(ASOF+'T12:00:00Z')")
R("Loaded new data: prices through", "Loaded new data: NAV through", count=0)
R("You already have the latest data (prices through", "You already have the latest data (NAV through")
R("'Could not load the ETF list. Reload the page.'", "'Could not load the Thai fund list. The data may still be building; try again later.'")
R("Last close ${fmtDate(d)}", "Last NAV ${fmtDate(d)}")
R("Stale · last close ${fmtDate(d)}", "Stale · last NAV ${fmtDate(d)}")
R("let MCP=null;", "let MCP=null; /* no on-demand rebuild for the Thai page: the button re-checks the published data */")
R("MCP = window.claude && claude.use ? await claude.use('mcp') : null;", "MCP = null;")
R("holdings: EXAMPLE.holdings.map(([t,w],i)=>", "holdings: EXAMPLE.holdings.filter(([t])=>D.meta[t]).map(([t,w],i)=>")

# fund database returns (only shown when the dataset carries them)
R('<p class="foot" id="perfNote"></p>', '''<p class="foot" id="perfNote"></p>
    <div id="dbBox" hidden style="margin-top:18px">
      <h3 style="margin:0 0 4px;font-size:15px">Fund database returns</h3>
      <p class="sub" style="font-size:13px;margin:0 0 8px" id="dbSub"></p>
      <div class="tscroll"><table class="perf" id="dbPerf"></table></div>
      <p class="foot" id="dbNote"></p>
    </div>''')
R("DATES=j.dates; N=DATES.length;", "DATES=j.dates; N=DATES.length; D.dbcols=j.dbcols||[]; D.dbasof=j.dbasof;")
R("renderChart(); renderPerf();", "renderChart(); renderPerf(); renderDb();")
R("/* ---------- performance table ---------- */", '''/* ---------- fund database returns ---------- */
function renderDb(){
  const box=document.getElementById('dbBox'); const cols=D.dbcols||[];
  if(!cols.length){ box.hidden=true; return; }
  const pw=portfolioWeights(); const rows=[];
  if(pw) rows.push(['PORT','Portfolio']); S.holdings.forEach(h=>rows.push([h.t,h.t]));
  const dbOf=t=> t==='CASH' ? cols.map(()=>0) : ((D.meta[t]||{}).db||null);
  let html='<thead><tr><th>Fund</th>'+cols.map(c=>`<th>${c}</th>`).join('')+'</tr></thead><tbody>';
  rows.forEach(([k,label])=>{
    let vals;
    if(k==='PORT'){
      vals=cols.map((_,i)=>{ let s=0; for(const t in pw.wts){ const d=dbOf(t); const v=d&&d[i]; if(v==null) return null; s+=pw.wts[t]*v; } return s; });
    } else vals=(dbOf(k)||cols.map(()=>null));
    const sw = k==='PORT' ? INK : colorOf(k);
    html+=`<tr class="${k==='PORT'?'portrow':''}"><td><span class="tick"><span class="sw" style="background:${sw}"></span>${label}</span></td>`+vals.map(v=>`<td class="${cls(v)}">${pct(v)}</td>`).join('')+'</tr>';
  });
  html+='</tbody>'; document.getElementById('dbPerf').innerHTML=html; box.hidden=false;
  document.getElementById('dbSub').textContent=`From your fund database${D.dbasof?` (as of ${D.dbasof})`:''}. It covers 10 years and every calendar year since 2014, so it fills in history the daily NAV download does not reach yet.`;
  document.getElementById('dbNote').textContent='3Y, 5Y and 10Y are annualized; years are calendar-year returns. The portfolio row is the weighted average of the funds (yearly rebalancing) and shows "–" when any held fund has no figure for that column. Optionality cash uses '+CASHT+'.';
}
/* ---------- performance table ---------- */''')

open(sys.argv[2], 'w', encoding='utf8').write(src)
print('thai page ok', len(src))
