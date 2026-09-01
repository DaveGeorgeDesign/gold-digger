#!/usr/bin/env python3
"""Screen S&P 500 + FTSE 100 stocks against value criteria and write data.js for the dashboard.

Usage:
  python3 fetch_data.py                 # full universe
  python3 fetch_data.py --tickers AAPL SHEL.L
  python3 fetch_data.py --limit 20
"""
import argparse
import datetime as dt
import re
import json
import os
import sys
import time

import requests
import yfinance as yf
from bs4 import BeautifulSoup

OUT_FILE = "data.js"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

FALLBACK_SP500 = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "BRK-B", "JPM", "V", "XOM",
    "UNH", "JNJ", "WMT", "PG", "MA", "HD", "CVX", "MRK", "ABBV", "PEP",
    "KO", "BAC", "PFE", "CSCO", "TMO", "MCD", "CRM", "ABT", "CMCSA", "INTC",
    "VZ", "ADBE", "NKE", "DIS", "WFC", "TXN", "PM", "COP", "NEE", "BMY",
    "RTX", "ORCL", "HON", "UPS", "QCOM", "LOW", "T", "GS", "CAT", "IBM",
]
FALLBACK_FTSE100 = [
    "SHEL.L", "AZN.L", "HSBA.L", "ULVR.L", "BP.L", "GSK.L", "RIO.L", "REL.L",
    "DGE.L", "GLEN.L", "BATS.L", "AAL.L", "NG.L", "LSEG.L", "VOD.L", "PRU.L",
    "CPG.L", "BARC.L", "NWG.L", "LLOY.L", "TSCO.L", "IMB.L", "SSE.L", "LGEN.L",
    "STAN.L", "BT-A.L", "AV.L", "RKT.L", "EXPN.L", "AHT.L",
]
FALLBACK_FTSE250 = [
    "ITV.L", "EZJ.L", "WIZZ.L", "JDW.L", "GRG.L", "BWY.L", "DNLM.L", "PETS.L",
    "DOM.L", "TRN.L", "CURY.L", "SRP.L", "QQ.L", "CHG.L", "DRX.L", "HBR.L",
    "PAGE.L", "INVP.L", "MTO.L", "TATE.L", "SXS.L", "ROR.L", "BYG.L", "SAFE.L",
    "GFTU.L", "BBY.L", "REDD.L", "OSB.L", "PAG.L", "VTY.L",
]
# BIST 100 has no scrapeable Wikipedia constituents table, so this list is
# static; unknown/delisted tickers are skipped harmlessly at fetch time
BIST100 = [
    "AEFES.IS", "AGHOL.IS", "AKBNK.IS", "AKSA.IS", "AKSEN.IS", "ALARK.IS",
    "ANSGR.IS", "ARCLK.IS", "ASELS.IS", "ASTOR.IS", "BIMAS.IS", "BRSAN.IS",
    "BRYAT.IS", "CCOLA.IS", "CIMSA.IS", "DOAS.IS", "DOHOL.IS", "ECILC.IS",
    "EGEEN.IS", "EKGYO.IS", "ENJSA.IS", "ENKAI.IS", "EREGL.IS", "FROTO.IS",
    "GARAN.IS", "GESAN.IS", "GUBRF.IS", "HALKB.IS", "HEKTS.IS", "ISCTR.IS",
    "ISMEN.IS", "KCHOL.IS", "KONTR.IS", "KONYA.IS", "KOZAA.IS", "KOZAL.IS",
    "KRDMD.IS", "MAVI.IS", "MGROS.IS", "ODAS.IS", "OTKAR.IS", "OYAKC.IS",
    "PETKM.IS", "PGSUS.IS", "SAHOL.IS", "SASA.IS", "SISE.IS", "SKBNK.IS",
    "SMRTG.IS", "SOKM.IS", "TAVHL.IS", "TCELL.IS", "THYAO.IS", "TKFEN.IS",
    "TOASO.IS", "TSKB.IS", "TTKOM.IS", "TTRAK.IS", "TUKAS.IS", "TUPRS.IS",
    "TURSG.IS", "ULKER.IS", "VAKBN.IS", "VESBE.IS", "VESTL.IS", "YKBNK.IS",
    "ZOREN.IS", "ALBRK.IS", "AKFYE.IS", "AHGAZ.IS", "ALFAS.IS", "BERA.IS",
    "BIENY.IS", "CANTE.IS", "CWENE.IS", "ENERY.IS", "EUPWR.IS", "GWIND.IS",
    "IZENR.IS", "KCAER.IS", "KLSER.IS", "MIATK.IS", "OBAMS.IS", "REEDR.IS",
    "SDTTR.IS", "TABGD.IS", "YEOTK.IS",
]


def scrape_wiki_tickers(url, symbol_col_names, suffix=""):
    resp = requests.get(url, headers=UA, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for table in soup.find_all("table", class_="wikitable"):
        header = [th.get_text(strip=True) for th in table.find("tr").find_all("th")]
        col = next((i for i, h in enumerate(header) if h in symbol_col_names), None)
        if col is None:
            continue
        tickers = []
        for row in table.find_all("tr")[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) > col:
                sym = cells[col].get_text(strip=True)
                if sym and len(sym) <= 7:
                    tickers.append(sym.replace(".", "-") + suffix)
        if len(tickers) > 50:
            return tickers
    return []


def scrape_index(url, cols, fallback, label, suffix=""):
    try:
        tickers = scrape_wiki_tickers(url, cols, suffix=suffix)
        if suffix:
            tickers = [t.replace("--L", "-L").replace("-L", ".L") if t.endswith("-L") else t
                       for t in tickers]
    except Exception as e:
        print(f"{label} scrape failed ({e}), using fallback list", file=sys.stderr)
        tickers = []
    return tickers or fallback


def build_universe():
    sp500 = scrape_index("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
                         {"Symbol"}, FALLBACK_SP500, "S&P 500")
    ftse100 = scrape_index("https://en.wikipedia.org/wiki/FTSE_100_Index",
                           {"Ticker", "EPIC"}, FALLBACK_FTSE100, "FTSE 100", suffix=".L")
    ftse250 = scrape_index("https://en.wikipedia.org/wiki/FTSE_250_Index",
                           {"Ticker", "EPIC"}, FALLBACK_FTSE250, "FTSE 250", suffix=".L")
    ftse250 = [t for t in ftse250 if t not in set(ftse100)]
    print(f"Universe: {len(sp500)} S&P 500 + {len(ftse100)} FTSE 100 + "
          f"{len(ftse250)} FTSE 250 + {len(BIST100)} BIST 100")
    universe = {}
    for sym in sp500:
        universe[sym] = "S&P 500"
    for sym in ftse100:
        universe[sym] = "FTSE 100"
    for sym in ftse250:
        universe[sym] = "FTSE 250"
    for sym in BIST100:
        universe[sym] = "BIST 100"
    return universe


_fx_cache = {}
_rf_cache = []


def risk_free():
    """US 10-year Treasury yield in %, fetched once per run."""
    if not _rf_cache:
        try:
            v = float(yf.Ticker("^TNX").fast_info.last_price)
            _rf_cache.append(v if 0.5 < v < 12 else 4.3)
        except Exception:
            _rf_cache.append(4.3)
    return _rf_cache[0]


def usd_rate(currency):
    """Multiplier converting 1 unit of `currency` to USD."""
    if not currency:
        return None
    cur = "GBP" if currency == "GBp" else currency
    if cur == "USD":
        return 1.0
    if cur not in _fx_cache:
        try:
            _fx_cache[cur] = float(yf.Ticker(f"{cur}USD=X").fast_info.last_price)
        except Exception:
            _fx_cache[cur] = None
    return _fx_cache[cur]


def shares_change_5y(ticker):
    start = (dt.date.today() - dt.timedelta(days=5 * 365 + 45)).isoformat()
    s = ticker.get_shares_full(start=start)
    if s is None or len(s) < 2:
        return None
    first, last = float(s.iloc[0]), float(s.iloc[-1])
    if first <= 0:
        return None
    # share counts are not split-adjusted: scale the first observation by any
    # splits that occurred between the two dates
    try:
        splits = ticker.splits
        if splits is not None and not splits.empty:
            between = splits[(splits.index > s.index[0]) & (splits.index <= s.index[-1])]
            for ratio in between:
                if ratio > 0:
                    first *= float(ratio)
    except Exception:
        pass
    return (last - first) / first * 100.0


def statement_cagr(inc, row_names):
    """Annualised growth % of the first matching income-statement row over the
    available annual statements (Yahoo provides up to ~5 years).
    Returns (cagr_pct, span_years)."""
    try:
        if inc is None or inc.empty:
            return None, None
        row = None
        for name in row_names:
            if name in inc.index:
                row = inc.loc[name].dropna().sort_index()
                break
        if row is None or len(row) < 2:
            return None, None
        first, last = float(row.iloc[0]), float(row.iloc[-1])
        span = (row.index[-1] - row.index[0]).days / 365.25
        if first <= 0 or last <= 0 or span < 1:
            return None, None
        return ((last / first) ** (1 / span) - 1) * 100, round(span, 1)
    except Exception:
        return None, None


def dividend_status(ticker):
    """Returns (status, yearly_dict). status: 'none' | 'growing' | 'not_growing'."""
    d = ticker.dividends
    this_year = dt.date.today().year
    if d is None or d.empty:
        return "none", {}
    yearly = d.groupby(d.index.year).sum()
    yearly = yearly[yearly.index < this_year]  # complete years only
    recent = {int(y): round(float(v), 4) for y, v in yearly.tail(5).items()}
    if not recent or max(recent) < this_year - 1:
        return "none", recent  # stopped paying
    years = sorted(recent)
    if len(years) < 5:
        return "not_growing", recent  # <5yr payment history can't show 5yr growth
    vals = [recent[y] for y in years]
    grew = vals[-1] > vals[0] and all(b >= a * 0.99 for a, b in zip(vals, vals[1:]))
    return ("growing" if grew else "not_growing"), recent


def statement_value(df, row_names):
    """Latest annual value of the first matching statement row.
    Returns (value, fiscal_year, row_name)."""
    try:
        if df is None or df.empty:
            return None, None, None
        for name in row_names:
            if name in df.index:
                row = df.loc[name].dropna().sort_index()
                if len(row):
                    return float(row.iloc[-1]), row.index[-1].year, name
        return None, None, None
    except Exception:
        return None, None, None


def sentiment_fields(t, info, price):
    """Analyst consensus, target upside, momentum and positioning signals."""
    s = {
        "analystRating": info.get("recommendationMean"),
        "analystKey": info.get("recommendationKey"),
        "analystCount": info.get("numberOfAnalystOpinions"),
        "targetUpside": None, "vs200d": None, "shortPct": None,
        "upgrades3m": None, "downgrades3m": None,
    }
    tgt = info.get("targetMeanPrice")
    if tgt and price:
        s["targetUpside"] = round((tgt - price) / price * 100, 1)
    d200 = info.get("twoHundredDayAverage")
    if price and d200:
        s["vs200d"] = round((price - d200) / d200 * 100, 1)
    short = info.get("shortPercentOfFloat")
    if short is not None:
        s["shortPct"] = round(short * 100, 1)
    try:
        ud = t.upgrades_downgrades
        if ud is not None and not ud.empty and "Action" in ud.columns:
            idx = ud.index.tz_localize(None) if ud.index.tz is not None else ud.index
            recent = ud[idx >= dt.datetime.now() - dt.timedelta(days=90)]
            s["upgrades3m"] = int((recent["Action"] == "up").sum())
            s["downgrades3m"] = int((recent["Action"] == "down").sum())
    except Exception:
        pass
    return s


def screen_ticker(symbol):
    t = yf.Ticker(symbol)
    info = t.info
    name = info.get("shortName") or info.get("longName")
    if not name:
        return None
    notes = {}  # metric -> how a missing Yahoo value was approximated

    price_fx = usd_rate(info.get("currency"))
    fin_fx = usd_rate(info.get("financialCurrency") or info.get("currency"))

    mcap = info.get("marketCap")
    mcap_usd = mcap * price_fx if mcap and price_fx else None

    try:
        inc = t.income_stmt
    except Exception:
        inc = None

    net_income = info.get("netIncomeToCommon")
    if net_income is None:
        net_income = statement_value(
            inc, ("Net Income Common Stockholders", "Net Income"))[0]

    pe = info.get("trailingPE")
    if pe is None and mcap_usd and fin_fx and net_income and net_income > 0:
        pe = mcap_usd / (net_income * fin_fx)
        notes["pe"] = ("Computed: market cap ÷ net income to common - "
                       "Yahoo publishes no trailing P/E for this stock.")

    eps_cagr, eps_span = statement_cagr(inc, ("Diluted EPS", "Basic EPS"))
    peg = info.get("trailingPegRatio")
    # Yahoo has no analyst-consensus PEG for many stocks (insurers especially);
    # fall back to trailing growth, flagged so the UI can mark it
    if peg is None and pe and pe > 0:
        if eps_cagr and eps_cagr > 0:
            peg = pe / eps_cagr
            notes["peg"] = (
                f"Computed: P/E ÷ trailing EPS growth (+{eps_cagr:.1f}%/yr over "
                f"{eps_span}y of statements). No analyst-consensus PEG - treat with "
                f"care, trailing growth flatters cyclical earnings rebounds.")
        else:
            ni_cagr, ni_span = statement_cagr(
                inc, ("Net Income Common Stockholders", "Net Income"))
            if ni_cagr and ni_cagr > 0:
                peg = pe / ni_cagr
                notes["peg"] = (
                    f"Computed: P/E ÷ trailing net-income growth (+{ni_cagr:.1f}%/yr "
                    f"over {ni_span}y). No analyst-consensus PEG or usable EPS history "
                    f"- treat with care, trailing growth flatters cyclical rebounds.")

    try:
        bs = t.balance_sheet
    except Exception:
        bs = None

    debt = info.get("totalDebt")
    if debt is None:
        debt, debt_fy, _ = statement_value(bs, ("Total Debt", "Long Term Debt"))
        if debt is not None:
            notes["debt"] = (f"Total debt taken from the FY{debt_fy} balance sheet - "
                             f"Yahoo's summary field is missing.")
    cash = info.get("totalCash")
    if cash is None:
        cash = statement_value(bs, ("Cash And Cash Equivalents",))[0]
        if cash is None and debt is not None:
            notes["debt"] = (notes.get("debt", "") +
                             " No cash figure available - gross debt used.").strip()
    net_debt = debt - (cash or 0) if debt is not None else None

    fcf = info.get("freeCashflow")
    if not fcf or fcf <= 0:
        try:
            cf = t.cashflow
        except Exception:
            cf = None
        stmt_fcf, fcf_fy, _ = statement_value(cf, ("Free Cash Flow",))
        if stmt_fcf is None:
            ocf, fcf_fy, _ = statement_value(cf, ("Operating Cash Flow",))
            capex = statement_value(cf, ("Capital Expenditure",))[0] or 0
            stmt_fcf = ocf + capex if ocf is not None else None
        if stmt_fcf and stmt_fcf > 0:
            fcf = stmt_fcf
            notes["pfcf"] = (
                f"Computed: market cap ÷ free cash flow from the FY{fcf_fy} cash-flow "
                f"statement (operating cash flow less capex) - Yahoo's summary FCF "
                f"field is missing, common for banks and financials.")
    p_fcf = None
    if fcf and fcf > 0 and mcap_usd and fin_fx:
        p_fcf = mcap_usd / (fcf * fin_fx)

    # net debt / FCF: years of free cash flow to pay off all debt
    net_cash = net_debt is not None and net_debt <= 0
    nd_fcf = None
    if net_debt is not None and fcf and fcf > 0:
        nd_fcf = net_debt / fcf

    # closed-end investment trusts: asset managers with (almost) no employees.
    # NAV proxied by book value per share from the last reported balance sheet.
    employees = info.get("fullTimeEmployees")
    trust_name = info.get("longName") or name
    is_trust = ((employees is None or employees < 100)
                and (info.get("industry") == "Asset Management"
                     or (info.get("sector") == "Financial Services"
                         and re.search(r"\btrust\b", trust_name, re.I) is not None)))
    nav_disc = None
    if is_trust:
        bv = info.get("bookValue")
        px = info.get("currentPrice") or info.get("regularMarketPrice")
        if bv and bv > 0 and px and price_fx and fin_fx:
            px_major = px / 100 if info.get("currency") == "GBp" else px
            nav_disc = (px_major * price_fx - bv * fin_fx) / (bv * fin_fx) * 100

    shares_pct = shares_change_5y(t)
    if shares_pct is None:
        for row_name in ("Diluted Average Shares", "Basic Average Shares"):
            if inc is not None and not inc.empty and row_name in inc.index:
                row = inc.loc[row_name].dropna().sort_index()
                if len(row) >= 2 and float(row.iloc[0]) > 0:
                    span = (row.index[-1] - row.index[0]).days / 365.25
                    shares_pct = (float(row.iloc[-1]) - float(row.iloc[0])) / float(row.iloc[0]) * 100
                    notes["shares"] = (
                        f"Computed from average share counts in annual statements "
                        f"({span:.1f}y span, not a full 5y) - Yahoo has no share-count "
                        f"history for this stock.")
                    break

    div_status, div_years = dividend_status(t)

    roe = info.get("returnOnEquity")

    tax = statement_value(inc, ("Tax Provision",))[0]
    pretax = statement_value(inc, ("Pretax Income",))[0]
    tax_rate = tax / pretax if tax is not None and pretax and pretax > 0 else 0.21
    tax_rate = min(max(tax_rate, 0.0), 0.5)

    # ROIC = NOPAT / invested capital; Yahoo has no summary field for it
    roic = None
    ic = statement_value(bs, ("Invested Capital",))[0]
    ebit = statement_value(inc, ("EBIT", "Operating Income"))[0]
    if ic and ic > 0 and ebit is not None:
        roic = ebit * (1 - tax_rate) / ic * 100

    # WACC via CAPM: Ke = rf + beta x ERP; Kd = interest expense / total debt
    wacc = None
    if mcap_usd:
        rf = risk_free()
        crp = 4.0 if symbol.endswith(".IS") else 0.0  # Turkey country risk premium
        beta = info.get("beta")
        ke = rf + (min(max(beta, 0.2), 2.5) if beta is not None else 1.0) * 5.0 + crp
        d_usd = debt * fin_fx if debt and fin_fx else 0
        interest = statement_value(inc, ("Interest Expense",))[0]
        if interest and debt and debt > 0:
            kd = min(max(abs(interest) / debt * 100, rf * 0.5), 20)
        else:
            kd = rf + 1.5
        wacc = (mcap_usd * ke + d_usd * kd * (1 - tax_rate)) / (mcap_usd + d_usd)

    # ROCE = EBIT / capital employed (total assets - current liabilities), pre-tax
    roce = None
    assets = statement_value(bs, ("Total Assets",))[0]
    curr_liab = statement_value(bs, ("Current Liabilities",))[0]
    if ebit is not None and assets and curr_liab is not None and assets - curr_liab > 0:
        roce = ebit / (assets - curr_liab) * 100

    rev_cagr, rev_span = statement_cagr(inc, ("Total Revenue",))
    if rev_cagr is None:
        for alt in ("Operating Revenue", "Interest Income"):
            rev_cagr, rev_span = statement_cagr(inc, (alt,))
            if rev_cagr is not None:
                notes["rev"] = (
                    f'Computed from the "{alt}" line over {rev_span}y - this company '
                    f"reports no Total Revenue (typical for funds and some financials).")
                break

    passes = {
        "mcap": mcap_usd is not None and mcap_usd > 2e9,
        "pe": pe is not None and 0 < pe < 12,
        "peg": peg is not None and 0 < peg < 1,
        "shares": shares_pct is not None and shares_pct < 0,
        "dividend": div_status in ("none", "growing"),
        "debt": net_cash or (nd_fcf is not None and nd_fcf < 3),
        "pfcf": p_fcf is not None and p_fcf < 10,
    }

    return {
        "symbol": symbol,
        "name": name,
        "country": info.get("country") or {"L": "United Kingdom", "IS": "Turkey"}.get(
            symbol.rsplit(".", 1)[-1]),
        "exchange": {"L": "LSE", "IS": "BIST"}.get(symbol.rsplit(".", 1)[-1], "US"),
        "sector": info.get("sector"),
        "currency": info.get("currency"),
        "price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "wkLow": info.get("fiftyTwoWeekLow"),
        **sentiment_fields(t, info, info.get("currentPrice") or info.get("regularMarketPrice")),
        "mcapUsd": round(mcap_usd) if mcap_usd else None,
        "pe": round(pe, 2) if pe is not None else None,
        "peg": round(peg, 2) if peg is not None else None,
        "notes": notes,
        "sharesPct5y": round(shares_pct, 1) if shares_pct is not None else None,
        "divStatus": div_status,
        "divYears": div_years,
        "netDebtFcf": round(nd_fcf, 2) if nd_fcf is not None else None,
        "netCash": net_cash,
        "isTrust": is_trust,
        "navDisc": round(nav_disc, 1) if nav_disc is not None else None,
        "pFcf": round(p_fcf, 2) if p_fcf is not None else None,
        "revCagr": round(rev_cagr, 1) if rev_cagr is not None else None,
        "revSpan": rev_span,
        "roic": round(roic, 1) if roic is not None else None,
        "wacc": round(wacc, 1) if wacc is not None else None,
        "roce": round(roce, 1) if roce is not None else None,
        "roe": round(roe * 100, 1) if roe is not None else None,
        "passes": passes,
        "passCount": sum(passes.values()),
        "passAll": all(passes.values()),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", nargs="+")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--out", default=OUT_FILE)
    args = ap.parse_args()

    if args.tickers:
        universe = {t: None for t in args.tickers}
    else:
        universe = build_universe()
    if args.limit:
        universe = dict(list(universe.items())[: args.limit])

    results, skipped = [], []
    for i, (sym, index) in enumerate(universe.items(), 1):
        try:
            row = screen_ticker(sym)
            if row:
                row["index"] = index or ("FTSE" if sym.endswith(".L") else "S&P 500")
                results.append(row)
            else:
                skipped.append(sym)
        except Exception as e:
            skipped.append(sym)
            print(f"  ! {sym}: {e}", file=sys.stderr)
        if i % 10 == 0 or i == len(universe):
            n_pass = sum(1 for r in results if r["passAll"])
            print(f"[{i}/{len(universe)}] screened, {n_pass} pass all criteria")
        time.sleep(0.3)

    payload = {
        "generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "universe": len(universe),
        "skipped": skipped,
        "stocks": results,
    }
    tmp = args.out + ".tmp"
    with open(tmp, "w") as f:
        f.write("const STOCK_DATA = ")
        json.dump(payload, f)
        f.write(";\n")
    os.replace(tmp, args.out)
    print(f"Wrote {len(results)} stocks to {args.out} ({len(skipped)} skipped)")


if __name__ == "__main__":
    main()
