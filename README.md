# ETF Portfolio Lab

A light-theme, single-page dashboard for comparing US-listed ETFs and testing portfolio allocations.

- Pick any of ~5,700 US ETFs. See a total-return chart (1D to ALL) and a performance table (1M to 20Y, volatility, max drawdown).
- Track each fund and the whole portfolio. The default portfolio is VT 40, QQQ 5, SMH 5, VDC 10, XLV 10, SCHD 10, SGOV 15, Optionality 5. Thai feeder fund labels are optional.
- Optimize the weights in the browser with these models:
  - equal weight and inverse volatility
  - Ledoit-Wolf shrinkage min-variance and max Sharpe
  - Black-Litterman with your own views
  - risk parity (ERC) and hierarchical risk parity (HRP)
  - Mean-CVaR and max diversification
- Compare the models side by side and stress-test them in the simulator (return estimation noise, correlation spikes).

Everything runs client-side. There is no server and no build step for the page.

## Layout

| Path | What it is |
| --- | --- |
| `index.html` | The whole app (HTML, CSS, JS; Chart.js from cdnjs). |
| `scripts/refresh.py` | Rebuilds the dataset into `<workdir>/out/` (`etfs.json` plus `d/<k>.json` shards). |
| `thai/scripts/sec_fetch.py` | Downloads Thai fund NAV, dividends and fund profiles from the SEC Thailand Open API. |
| `thai/scripts/build.py` | Turns that into the same `etfs.json` + shards format for the Thai page. |
| `thai/scripts/make_page.py` | Generates `thai/index.html` from `index.html`, so both pages share one codebase. |
| `.github/workflows/refresh-and-deploy.yml` | Rebuilds both datasets Tue–Sat at 10:47 Bangkok time and deploys to GitHub Pages. |

The data files (~31 MB) are generated, not committed.

## Data

- Prices and dividends come from the public Yahoo mirror at [`alm0421/alm0421`](https://github.com/alm0421/alm0421) (`data/prices/<TICKER>.csv`, `data/funds_meta.json`).
- Total return is rebuilt from close plus dividend, because the mirror's `adj_close` lags recent payouts. A few missing dividends (SGOV, VT, QQQ, SMH) are filled from `a23882005/LivingWaterAI`.
- Data cleaning:
  - One-day spikes greater than 1.6× that reverse the next day are removed as bad ticks.
  - Funds with no data for more than 35 days are dropped.
- **VHYA** (Vanguard FTSE All-World High Dividend Yield UCITS, USD Acc) is not US-listed, so it is a **proxy**:
  - 38.5% VYM plus 61.5% VYMI, rebalanced monthly
  - minus a 0.16%/yr fee gap
  - Further proxies are added in `PROXIES` in `refresh.py`.

This is for research and education, not investment advice.

## Thai fund version (`/thai`)

This page has the same charts, table, optimizers and simulator as the US page, but uses Thai mutual funds: every class, including RMF, SSF and Thai ESG.

- **Data:** daily NAV and dividends since 2016, from the [SEC Thailand Open API](https://api-portal.sec.or.th). Total return reinvests each dividend on the day the NAV goes ex-dividend. Returns are in baht.
- **Key:** set it up once by saving a free SEC Open API key as the repository secret `SEC_API_KEY` (or `InvestorBotFundNAV`). The key needs the fund general-info, factsheet and daily-info products.
- **History:** stored on the `thai-data` branch.
  - The first run downloads about 10 years of NAV, which takes a few hours. The page fills in as it goes.
  - Later runs only fetch the latest two months.
- **Other conventions:**
  - **Cash and Sharpe ratio:** "Optionality" cash and the Sharpe ratio use the largest Thai money-market fund.
  - **Annualizing:** uses the number of Thai NAV days per year.

## Run locally

```bash
python3 -I scripts/refresh.py ./work      # ~2 min, needs curl and internet
cp index.html work/out/
cd work/out && python3 -m http.server 8000
# open http://localhost:8000
```

The page has to be served over HTTP, not opened as a file, because it fetches `etfs.json` and its shards.

## Deploy on GitHub Pages

1. Go to **Settings → Pages** and set **Source** to **GitHub Actions**.
2. Go to **Actions → Refresh data and deploy** and click **Run workflow**. It also runs on every push to `main` and on the daily schedule.

On Pages, the **Refresh data** button checks for a newer published dataset. The Action is what rebuilds it.
