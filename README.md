# Gold Digger

A stock-screening dashboard for S&P 500 + FTSE 100 + FTSE 250 + BIST 100
stocks, in three tabs:

- **Screener** - operating companies against the 9 value criteria below
- **Investment Trusts** - closed-end trusts only, sorted by NAV discount
  (trusts pass value screens artificially, so they live separately)
- **Buffett** - a 5-rule balance-sheet check: more cash than borrowings,
  liabilities/equity under 0.8, no preferred stock, retained earnings growing
  every year, and treasury stock held

Screener criteria:

1. Market cap over $2bn
2. P/E ratio under 12
3. PEG ratio under 1

Where Yahoo lacks a summary value (PEG, P/E, P/FCF, revenue, share history,
debt), a best-effort fallback is computed from the financial statements and
shown in italics with a * - its tooltip explains the exact computation. Values
that can't be honestly approximated (e.g. growth from a loss-making base year)
stay as "–".
4. Shares in issue declined over the last 5 years (split-adjusted)
5. If paying a dividend, the dividend grew over the last 5 complete years (no dividend = pass)
6. Net debt (total debt minus cash) less than 3 years' free cash flow
   (a net cash position passes automatically)
7. Price to free cash flow under 10

All values are normalised to USD for the market cap and P/FCF checks. Data comes
from Yahoo Finance via the `yfinance` library - no API key needed.

## Viewing

```
python3 serve.py
```

Then visit http://localhost:4380. The server auto-refreshes the data from
yfinance whenever it is more than 24 hours old (checked on page load and once
a minute while the page is open), shows live progress in the header, and
reloads the page when the refresh finishes. There is also a "Refresh now"
button.

Opening `index.html` directly also works - you just get a static view with no
refresh support.

- Click the criteria chips to include/exclude individual rules
- Untick "Only stocks passing all criteria" to see near-misses ranked by score
- Filter by country, exchange or sector; click column headers to sort

## Refreshing manually

```
python3 fetch_data.py
```

Takes 25-40 minutes for the full universe (rate-limit friendly). Rewrites
`data.js`, which the page reads on load. The dashboard header shows an amber
warning if the data is more than 2 days old. Useful flags:

- `--tickers AAPL SHEL.L` - screen specific tickers only
- `--limit 50` - first N of the universe (quick test)

The ticker universe is scraped from Wikipedia's S&P 500, FTSE 100 and FTSE 250
pages at run time, with embedded fallback lists if that fails. BIST 100 has no
scrapeable constituents page, so it uses a static list in `fetch_data.py` -
edit `BIST100` there to add or remove Turkish stocks.
