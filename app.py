
import re
import sqlite3
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from solutions import SOLUTIONS

st.set_page_config(page_title="Stock Market Dashboard", page_icon="📈", layout="wide")

@st.cache_data
def load():
    con = sqlite3.connect("stocks.db")
    d = pd.read_sql("SELECT * FROM stocks", con, parse_dates=["date"])
    con.close()
    return d

df = load()

# ---------- sidebar filters ----------
st.sidebar.header("Filters")
all_stocks = sorted(df["stock"].unique())
stocks = st.sidebar.multiselect("Stocks", all_stocks, default=all_stocks)
dmin, dmax = df["date"].min().date(), df["date"].max().date()
dr = st.sidebar.slider("Date range", dmin, dmax, (dmin, dmax))
f = df[df["stock"].isin(stocks) & (df["date"].dt.date >= dr[0]) & (df["date"].dt.date <= dr[1])]
if f.empty:
    st.warning("Pick at least one stock.")
    st.stop()

def summary(d):
    rows = []
    for s, g in d.groupby("stock"):
        g = g.sort_values("date")
        a, b = g["close_price"].iloc[0], g["close_price"].iloc[-1]
        rows.append({"Stock": s, "Start Close": a, "End Close": b,
                     "Change %": round((b - a) / a * 100, 1),
                     "Avg Daily Return %": round(g["daily_return"].mean(), 3),
                     "Volatility %": round(g["daily_return"].std(), 2),
                     "Avg Delivery %": round(g["deli_pct"].mean(), 1)})
    return pd.DataFrame(rows)

sm = summary(f)

st.title("📈 Stock Market Analysis Dashboard")
st.info("TCS and Infosys prices are adjusted for their 1:1 bonus issues. Column raw_close keeps the original price.")
tabs = st.tabs(["🏠 Overview", "🔍 EDA", "🚀 Performance", "🎯 Signals", "🧪 SQL Playground"])

# ---------- Overview ----------
with tabs[0]:
    best, worst = sm.loc[sm["Change %"].idxmax()], sm.loc[sm["Change %"].idxmin()]
    st.success(f"Best performer: **{best['Stock']}** ({best['Change %']}%) | "
               f"Weakest: **{worst['Stock']}** ({worst['Change %']}%)")
    cols = st.columns(len(sm))
    for c, (_, r) in zip(cols, sm.iterrows()):
        c.metric(r["Stock"], f"₹{r['End Close']:,.0f}", f"{r['Change %']}%")
    st.dataframe(sm, use_container_width=True, hide_index=True)
    fig = px.bar(sm, x="Stock", y="Change %", color="Change %",
                 color_continuous_scale="RdYlGn", title="Total % change in selected period")
    st.plotly_chart(fig, use_container_width=True)

# ---------- EDA ----------
with tabs[1]:
    s = st.selectbox("Stock", stocks, key="eda_stock")
    d = f[f["stock"] == s]
    kind = st.radio("Chart type", ["Line + MA", "Candlestick"], horizontal=True)
    fig = go.Figure()
    if kind == "Candlestick":
        fig.add_trace(go.Candlestick(x=d["date"], open=d["open_price"], high=d["high_price"],
                                     low=d["low_price"], close=d["close_price"], name="Price"))
    else:
        fig.add_trace(go.Scatter(x=d["date"], y=d["close_price"], name="Close"))
    fig.add_trace(go.Scatter(x=d["date"], y=d["ma20"], name="MA20"))
    fig.add_trace(go.Scatter(x=d["date"], y=d["ma50"], name="MA50"))
    fig.update_layout(title=f"{s} price", xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    c1.plotly_chart(px.bar(d, x="date", y="shares", title="Volume (shares traded)"),
                    use_container_width=True)
    c2.plotly_chart(px.histogram(d.dropna(subset=["daily_return"]), x="daily_return",
                                 nbins=50, title="Daily return distribution (%)"),
                    use_container_width=True)

    if len(stocks) > 1:
        corr = f.pivot(index="date", columns="stock", values="daily_return").corr()
        st.plotly_chart(px.imshow(corr, text_auto=".2f", color_continuous_scale="RdBu_r",
                                  title="Correlation of daily returns"),
                        use_container_width=True)
    with st.expander("Summary statistics"):
        st.dataframe(d[["open_price", "high_price", "low_price", "close_price",
                        "shares", "turnover", "deli_pct"]].describe())

# ---------- Performance ----------
with tabs[2]:
    n = f.sort_values("date").copy()
    n["growth"] = n["close_price"] / n.groupby("stock")["close_price"].transform("first") * 100
    st.plotly_chart(px.line(n, x="date", y="growth", color="stock",
                            title="Growth of 100 (all stocks start at 100)"),
                    use_container_width=True)
    st.plotly_chart(px.scatter(sm, x="Volatility %", y="Avg Daily Return %", text="Stock",
                               size="Avg Delivery %", color="Stock",
                               title="Risk vs Return"), use_container_width=True)
    st.subheader("💰 If I had invested...")
    amt = st.number_input("Amount (₹)", value=10000, step=1000)
    inv = sm[["Stock", "Change %"]].copy()
    inv["Final Value (₹)"] = (amt * (1 + inv["Change %"] / 100)).round(0)
    st.dataframe(inv, use_container_width=True, hide_index=True)

# ---------- Signals ----------
with tabs[3]:
    s = st.selectbox("Stock", stocks, key="sig_stock")
    d = f[f["stock"] == s]
    fig = go.Figure(go.Scatter(x=d["date"], y=d["close_price"], name="Close"))
    for sig, color, sym in [("BUY", "green", "triangle-up"), ("SELL", "red", "triangle-down")]:
        p = d[d["signal"] == sig]
        fig.add_trace(go.Scatter(x=p["date"], y=p["close_price"], mode="markers", name=sig,
                                 marker=dict(color=color, size=12, symbol=sym)))
    fig.update_layout(title=f"{s} buy/sell signals (MA20 crossing MA50)")
    st.plotly_chart(fig, use_container_width=True)

    rows = []
    for st_name, g in f.sort_values("date").groupby("stock"):
        last = g.dropna(subset=["ma50"]).iloc[-1]
        rows.append({"Stock": st_name, "Buy signals": (g["signal"] == "BUY").sum(),
                     "Sell signals": (g["signal"] == "SELL").sum(),
                     "Current trend": "Up ⬆️" if last["ma20"] > last["ma50"] else "Down ⬇️"})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ---------- SQL Playground: helpers ----------
TABLES = {"bajaj_auto": "Bajaj_Auto.csv", "eicher_motors": "Eicher_Motors.csv",
          "hero_motocorp": "Hero_Motocorp.csv", "infosys": "Infosys.csv",
          "tcs": "TCS.csv", "tvs_motors": "TVS_Motors.csv"}
COLS = ["date", "open_price", "high_price", "low_price", "close_price", "wap",
        "no_of_shares", "no_of_trades", "total_turnover", "deliverable_qty",
        "pct_deli_qty", "spread_high_low", "spread_close_open"]

def build_db():
    con = sqlite3.connect(":memory:", check_same_thread=False)
    for t, path in TABLES.items():
        d = pd.read_csv(path)
        d["Date"] = pd.to_datetime(d["Date"], format="%d-%B-%Y").dt.strftime("%Y-%m-%d")
        d.columns = COLS
        d.sort_values("date").to_sql(t, con, index=False)
    src = sqlite3.connect("stocks.db")
    pd.read_sql("SELECT * FROM stocks", src).to_sql("stocks", con, index=False)
    src.close()
    return con

def split_sql(sql):
    stmts, cur = [], ""
    for line in sql.splitlines(True):
        cur += line
        if sqlite3.complete_statement(cur):
            stmts.append(cur.strip()); cur = ""
    rest = "\n".join(l for l in cur.splitlines() if l.strip() and not l.strip().startswith("--"))
    if rest.strip():
        stmts.append(cur.strip())
    return stmts

BLOCKED = re.compile(r"\b(attach|detach|pragma|load_extension|vacuum)\b", re.I)

def run_sql(con, sql):
    stmts = split_sql(sql)
    if not stmts:
        raise ValueError("Write a query first.")
    last = None
    for s in stmts:
        if BLOCKED.search(s):
            raise ValueError("ATTACH, PRAGMA and similar commands are not allowed.")
        cur = con.execute(s)
        if cur.description:
            last = pd.DataFrame(cur.fetchall(), columns=[c[0] for c in cur.description])
    con.commit()
    return last, len(stmts)

TASKS = {
"1. How much history?": ("Return the number of trading days, first date and last date in bajaj_auto.",
"SELECT ___ (*) AS trading_days,\n ___ (date) AS first_day,\n ___ (date) AS last_day\nFROM bajaj_auto;",
"One row, three columns. Just under 900 days. First day 2015-01-01, last day 2018-07-31."),
"2. Eicher's five best closes": ("Date and close_price of Eicher's five highest closes, highest first.",
"SELECT date, close_price\nFROM eicher_motors\nORDER BY ___ ___\nLIMIT ___;",
"Five rows. Top close above 32,000. All five dates fall in the same month."),
"3. TCS, year by year": ("Each year and TCS's average close for that year (2 decimals), oldest first.",
"SELECT strftime('%Y', date) AS year,\n ___(___(close_price), 2) AS avg_close\nFROM tcs\nGROUP BY ___\nORDER BY ___;",
"Four rows (2015-2018). The 2016 average is exactly 2419.00. 2018 has only 7 months."),
"4. Find the holes": ("Across all six tables, return stock name and date of every row where deliverable_qty is NULL.",
"SELECT 'bajaj_auto' AS stock, date FROM bajaj_auto WHERE deliverable_qty ___\nUNION ALL\n-- repeat for the other five tables (only the last SELECT gets a semicolon)\n;",
"Six rows in total, one per stock, on only two distinct dates."),
"5. Moving averages (bajaj1)": ("Create table bajaj1 with date, close_price, ma20, ma50 (rounded to 2). NULL until a full window exists.",
"DROP TABLE IF EXISTS bajaj1;\nCREATE TABLE bajaj1 AS\nSELECT date, close_price,\n CASE WHEN ROW_NUMBER() OVER (ORDER BY date) >= ___\n THEN ROUND(AVG(close_price) OVER (___), 2)\n END AS ma20\n -- ma50: same idea, you write it\nFROM bajaj_auto;\nSELECT * FROM bajaj1;",
"889 rows, 4 columns. First ma20 on 2015-01-29 = 2415.53. First ma50 on 2015-03-13 = 2283.80. On 2018-07-31 ma20 = 2918.51."),
"6. Master table": ("Create master_table: date, bajaj, tcs, tvs, infosys, eicher, hero (closing prices).",
"DROP TABLE IF EXISTS master_table;\nCREATE TABLE master_table AS\nSELECT b.date,\n b.close_price AS bajaj,\n t.close_price AS tcs\n -- add tvs, infosys, eicher, hero\nFROM bajaj_auto b\nJOIN tcs t ON t.date = b.date\n-- three more joins\n;\nSELECT * FROM master_table;",
"889 rows, 7 columns, no NULLs. On 2018-07-31: bajaj 2700.70 and tvs 517.45."),
"7. Golden cross signals (bajaj2)": ("From bajaj1 create bajaj2 with date, close_price, signal (Buy / Sell / Hold).",
"DROP TABLE IF EXISTS bajaj2;\nCREATE TABLE bajaj2 AS\nWITH t AS (\n SELECT date, close_price, ma20, ma50,\n LAG(ma20) OVER (ORDER BY date) AS prev_ma20,\n ___ AS prev_ma50\n FROM bajaj1\n)\nSELECT date, close_price,\n CASE\n WHEN ___ IS NULL OR ___ IS NULL THEN 'Hold'\n WHEN ma20 > ma50 AND prev_ma20 ___ prev_ma50 THEN 'Buy'\n WHEN ___ THEN 'Sell'\n ELSE 'Hold'\n END AS signal\nFROM t;\nSELECT * FROM bajaj2 WHERE signal <> 'Hold';",
"889 rows, 3 columns. First Buy 2015-05-18. First Sell 2015-08-24. Only a few dozen Buy/Sell days."),
"8. How often did it trigger?": ("From bajaj2 return each signal and its number of days, sorted by signal.",
"SELECT signal, COUNT(*) AS days\nFROM bajaj2\nGROUP BY ___\nORDER BY ___;",
"Three rows. Counts add up to 889. Bajaj has 12 Buys and 11 Sells."),
"9. Signal on a given day": ("Return the signal from bajaj2 for 2018-06-21.",
"SELECT ___\nFROM bajaj2\nWHERE date = '2018-06-21';",
"One row. Test first with 2015-05-18 (Buy) and 2016-01-04 (Hold). In MySQL you turn this into a function."),
"10. All six stocks in one query": ("One row per stock: buys, sells, last_signal_date, last_signal. Use PARTITION BY.",
"WITH prices AS (\n SELECT 'Bajaj Auto' AS stock, date, close_price FROM bajaj_auto\n UNION ALL\n SELECT 'TCS', date, close_price FROM tcs\n -- four more\n),\nma AS (\n -- task 5 logic, PARTITION BY stock in every OVER\n),\nlagged AS (\n -- task 7 lags, partitioned\n),\nsig AS (\n -- task 7 CASE\n),\nlatest AS (\n -- non-Hold rows, ROW_NUMBER() newest-first per stock\n)\nSELECT 1;",
"Six rows, five columns. Total 56 Buys and 57 Sells across all stocks. Bajaj row matches tasks 8 and 9."),
"11. Who went up?": ("For each stock: first_close, last_close, pct_change (1 decimal), biggest gain first.",
"WITH ends AS (\n SELECT stock, MIN(date) AS first_d, MAX(date) AS last_d\n FROM stocks GROUP BY stock\n)\nSELECT e.stock, f.raw_close AS first_close, l.raw_close AS last_close,\n ROUND(100.0 * (l.raw_close - f.raw_close) / f.raw_close, 1) AS pct_change\nFROM ends e\nJOIN stocks f ON ___\nJOIN stocks l ON ___\nORDER BY pct_change DESC;",
"Six rows. TVS Motors tops at 86.9%. Two stocks are negative (TCS and Infosys on raw prices)."),
"12. The data trap": ("For each stock find the single worst day: stock, date, close_price, pct_move (1 decimal), worst first.",
"WITH moves AS (\n SELECT stock, date, raw_close AS close_price,\n 100.0 * (raw_close / LAG(raw_close) OVER (PARTITION BY stock ORDER BY date) - 1) AS pct_move\n FROM stocks\n),\nranked AS (\n SELECT *, ROW_NUMBER() OVER (PARTITION BY stock ORDER BY pct_move) AS rn\n FROM moves WHERE pct_move IS NOT NULL\n)\nSELECT stock, date, close_price, ROUND(pct_move, 1) AS pct_move\nFROM ranked WHERE rn = ___\nORDER BY pct_move;",
"Six rows. Most worst days are between -6% and -10%. Two rows are about -50%: that is the bonus issue, not a real crash."),
"13. Fix it": ("Adjust TCS and Infosys prices for the events you found, then return stock and adjusted_pct_change.",
"WITH adjusted AS (\n SELECT 'TCS' AS stock, date,\n CASE WHEN date < '___' THEN close_price / 2 ELSE close_price END AS adj_close\n FROM tcs\n UNION ALL\n ___\n)\nSELECT stock,\n ROUND(100.0 * (MAX(CASE WHEN date = '___' THEN adj_close END) /\n MAX(CASE WHEN date = '___' THEN adj_close END) - 1), 1) AS adjusted_pct_change\nFROM adjusted\nGROUP BY stock\nORDER BY stock;",
"Two rows. Search each stock name + the cliff date with 'bonus issue' to confirm the event. Compare with task 11."),
"Free practice (merged table)": ("Query the merged table `stocks` (adjusted prices, signals, MA20/MA50).",
"SELECT stock, SUM(signal='BUY') AS buys, SUM(signal='SELL') AS sells\nFROM stocks\nGROUP BY stock;", "Any SELECT works here."),
}

# ---------- SQL Playground ----------
with tabs[4]:
    if "db" not in st.session_state:
        st.session_state.db = build_db()
    st.write("A live SQL playground on the 6 original tables, plus the merged table `stocks`. "
             "You can use CREATE TABLE, DROP TABLE, CTEs and window functions. Your changes live only in this session.")
    top1, top2 = st.columns([4, 1])
    task = top1.selectbox("Pick a task from the student guide", list(TASKS))
    if top2.button("♻ Reset database"):
        st.session_state.db = build_db()
        st.success("Database reset.")
    goal, skeleton, checks = TASKS[task]
    st.markdown(f"**Goal:** {goal}")
    st.info(f"**Check yourself:** {checks}")
    q = st.text_area("Your SQL (fill the ___ blanks)", value=skeleton, height=300, key="sql_" + task)
    if st.button("▶ Run query", type="primary"):
        if "___" in q:
            st.warning("Fill in the ___ blanks first, then run.")
        else:
            try:
                out, n = run_sql(st.session_state.db, q)
                st.success(f"{n} statement(s) ran.")
                if out is not None:
                    st.write(f"{len(out)} rows, {len(out.columns)} columns")
                    st.dataframe(out, use_container_width=True)
                    st.download_button("Download CSV", out.to_csv(index=False), "query_result.csv")
            except Exception as e:
                st.error(f"SQL error: {e}")
                
    if task in SOLUTIONS:
        with st.expander("💡 Show solution"):
            st.code(SOLUTIONS[task], language="sql")
    with st.expander("Tables in this database"):
        tl = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name",
                         st.session_state.db)
        for t in tl["name"]:
            cnt = st.session_state.db.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            cols = [r[1] for r in st.session_state.db.execute(f'PRAGMA table_info("{t}")')]
            st.write(f"**{t}** ({cnt} rows): " + ", ".join(cols))