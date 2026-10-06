
# Merge + clean + EDA in one script
import sqlite3, os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---------- 1. MERGE ----------
files = {
    "Bajaj Auto": "Bajaj_Auto.csv",
    "Eicher Motors": "Eicher_Motors.csv",
    "Hero Motocorp": "Hero_Motocorp.csv",
    "Infosys": "Infosys.csv",
    "TCS": "TCS.csv",
    "TVS Motors": "TVS_Motors.csv",
}
frames = []
for name, path in files.items():
    d = pd.read_csv(path)
    d["Stock"] = name
    frames.append(d)
df = pd.concat(frames, ignore_index=True)

# ---------- 2. CLEAN ----------
df["Date"] = pd.to_datetime(df["Date"], format="%d-%B-%Y")
df = df.sort_values(["Stock", "Date"]).reset_index(drop=True)
df = df.rename(columns={
    "Date": "date", "Stock": "stock", "Open Price": "open_price",
    "High Price": "high_price", "Low Price": "low_price",
    "Close Price": "close_price", "WAP": "wap", "No.of Shares": "shares",
    "No. of Trades": "trades", "Total Turnover (Rs.)": "turnover",
    "Deliverable Quantity": "deliverable_qty",
    "% Deli. Qty to Traded Qty": "deli_pct",
    "Spread High-Low": "spread_high_low",
    "Spread Close-Open": "spread_close_open"})
print("Missing values before fixing:")
print(df.isna().sum()[df.isna().sum() > 0])
df = df.fillna(df.median(numeric_only=True))

# bonus-issue fix (TCS 2018-05-31, Infosys 2015-06-15)
df["raw_close"] = df["close_price"]
events = {"TCS": "2018-05-31", "Infosys": "2015-06-15"}
for s, ev in events.items():
    m = (df["stock"] == s) & (df["date"] < pd.Timestamp(ev))
    df.loc[m, ["open_price", "high_price", "low_price", "close_price", "wap"]] /= 2

# ---------- 3. FEATURES ----------
g = df.groupby("stock")["close_price"]
df["daily_return"] = g.pct_change() * 100
df["ma20"] = g.transform(lambda s: s.rolling(20).mean())
df["ma50"] = g.transform(lambda s: s.rolling(50).mean())
above = df["ma20"] > df["ma50"]
prev_above = above.groupby(df["stock"]).shift()
prev_ok = df.groupby("stock")["ma50"].shift().notna()
df["signal"] = ""
df.loc[above & (prev_above == False) & prev_ok, "signal"] = "BUY"
df.loc[~above & (prev_above == True) & prev_ok, "signal"] = "SELL"

# ---------- 4. SAVE ----------
out = df.copy()
out["date"] = out["date"].dt.strftime("%Y-%m-%d")
out.to_csv("stocks_merged.csv", index=False)
con = sqlite3.connect("stocks.db")
out.to_sql("stocks", con, index=False, if_exists="replace")
con.close()
print("\nMerged shape:", df.shape)
print(df["stock"].value_counts())

# ---------- 5. EDA (text) ----------
print("\nSummary statistics:")
print(df[["open_price", "close_price", "shares", "turnover", "deli_pct"]].describe().round(2))
summ = df.groupby("stock").agg(
    start=("close_price", "first"), end=("close_price", "last"),
    avg_return=("daily_return", "mean"), volatility=("daily_return", "std"),
    avg_volume=("shares", "mean"))
summ["change_pct"] = (summ["end"] / summ["start"] - 1) * 100
print("\nPer-stock performance:")
print(summ.round(2))
print("\nBuy/Sell counts:")
print(df.groupby("stock")["signal"].value_counts().unstack(fill_value=0).drop(columns="", errors="ignore"))

# ---------- 6. EDA (charts saved as PNG) ----------
os.makedirs("eda_charts", exist_ok=True)
stocks = list(files)

fig, axes = plt.subplots(3, 2, figsize=(13, 10))
for ax, s in zip(axes.flat, stocks):
    d = df[df.stock == s]
    ax.plot(d["date"], d["close_price"], label="Close")
    ax.plot(d["date"], d["ma20"], label="MA20")
    ax.plot(d["date"], d["ma50"], label="MA50")
    ax.set_title(s); ax.legend(fontsize=7)
fig.suptitle("Price trend with MA20 / MA50 (adjusted)"); fig.tight_layout()
fig.savefig("eda_charts/1_price_trends.png", dpi=120); plt.close(fig)

fig, axes = plt.subplots(1, 2, figsize=(12, 4))
for ax, s in zip(axes, ["TCS", "Infosys"]):
    d = df[df.stock == s]
    ax.plot(d["date"], d["raw_close"], label="Raw (with cliff)")
    ax.plot(d["date"], d["close_price"], label="Adjusted")
    ax.set_title(f"{s}: before vs after bonus fix"); ax.legend()
fig.tight_layout(); fig.savefig("eda_charts/2_bonus_fix.png", dpi=120); plt.close(fig)

growth = df.assign(growth=df["close_price"] / g.transform("first") * 100)
fig, ax = plt.subplots(figsize=(11, 5))
for s in stocks:
    d = growth[growth.stock == s]; ax.plot(d["date"], d["growth"], label=s)
ax.set_title("Growth of 100 (adjusted)"); ax.legend(); fig.tight_layout()
fig.savefig("eda_charts/3_growth_of_100.png", dpi=120); plt.close(fig)

fig, ax = plt.subplots(figsize=(9, 4))
summ["avg_volume"].plot(kind="bar", ax=ax); ax.set_title("Average daily volume (shares)")
fig.tight_layout(); fig.savefig("eda_charts/4_avg_volume.png", dpi=120); plt.close(fig)

fig, axes = plt.subplots(3, 2, figsize=(12, 9))
for ax, s in zip(axes.flat, stocks):
    ax.hist(df[df.stock == s]["daily_return"].dropna(), bins=50); ax.set_title(s)
fig.suptitle("Daily return distribution (%)"); fig.tight_layout()
fig.savefig("eda_charts/5_return_histograms.png", dpi=120); plt.close(fig)

corr = df.pivot(index="date", columns="stock", values="daily_return").corr()
fig, ax = plt.subplots(figsize=(7, 6))
im = ax.imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1)
ax.set_xticks(range(6)); ax.set_xticklabels(corr.columns, rotation=45, ha="right")
ax.set_yticks(range(6)); ax.set_yticklabels(corr.columns)
for i in range(6):
    for j in range(6):
        ax.text(j, i, f"{corr.iloc[i, j]:.2f}", ha="center", va="center", fontsize=8)
fig.colorbar(im); ax.set_title("Correlation of daily returns"); fig.tight_layout()
fig.savefig("eda_charts/6_correlation.png", dpi=120); plt.close(fig)
print("\nSaved 6 charts in the eda_charts folder.")