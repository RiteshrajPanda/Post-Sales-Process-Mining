"""
Evening 3 — the analyses that carry the resume bullet:
  Q3  biggest rework loop (ping-pong)  — org:group handovers between teams
  Q4  the bottleneck                   — which activity has the longest wait
  Q5  the one driver                   — do reassignments predict resolution time?

Plain pandas for transparency; matplotlib for the two charts.
"""
import os
from collections import Counter
import numpy as np
import pandas as pd
import pm4py
from scipy import stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 160)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(BASE, "data", "BPI_Challenge_2013_incidents.xes.gz")
FIG_DIR = os.path.join(BASE, "figures")
os.makedirs(FIG_DIR, exist_ok=True)

CASE = "case:concept:name"
STATUS = "concept:name"
SUB = "lifecycle:transition"
GROUP = "org:group"
TS = "time:timestamp"

df = pm4py.read_xes(LOG_PATH).reset_index(drop=True)
df["evt_order"] = df.index
df["activity"] = df[STATUS].astype(str) + " / " + df[SUB].astype(str)
# Chronological order within each case (evt_order breaks timestamp ties).
df = df.sort_values([CASE, TS, "evt_order"]).reset_index(drop=True)

print(f"events={len(df):,}  cases={df[CASE].nunique():,}")
print(f"org:group nulls: {df[GROUP].isna().sum()}  "
      f"distinct teams: {df[GROUP].nunique()}")

# Q3  BIGGEST REWORK LOOP (PING-PONG between teams)
print("\n" + "=" * 70)
print("Q3  PING-PONG  (org:group handovers)")
print("=" * 70)

def collapse(seq):
    """Drop NaN, then collapse consecutive duplicates -> list of team visits."""
    out = []
    for x in seq:
        if pd.isna(x):
            continue
        if not out or out[-1] != x:
            out.append(x)
    return out

g = df.groupby(CASE, sort=False)
team_path = g[GROUP].apply(lambda s: collapse(list(s)))

# Reassignments per case = number of team changes.
n_reassign = team_path.apply(lambda p: max(len(p) - 1, 0))
print(f"Reassignments per case: mean={n_reassign.mean():.2f}  "
      f"median={n_reassign.median():.0f}  max={n_reassign.max()}")
print("Distribution:")
print(n_reassign.value_counts().sort_index().head(12).to_string())

# Directed handovers A->B and ping-pong bounces A->B->A.
handovers = Counter()
pingpong = Counter()        # unordered {A,B} that bounce back at least once
for p in team_path:
    for i in range(len(p) - 1):
        handovers[(p[i], p[i + 1])] += 1
    for i in range(len(p) - 2):
        if p[i] == p[i + 2] and p[i] != p[i + 1]:
            pingpong[frozenset((p[i], p[i + 1]))] += 1

print("\nTop 10 directed handovers (team -> team):")
for (a, b), c in handovers.most_common(10):
    print(f"  {c:>4}  {a} -> {b}")

print("\nTop 10 PING-PONG pairs (A->B->A bounce-backs):")
pp_sorted = sorted(pingpong.items(), key=lambda kv: kv[1], reverse=True)
for pair, c in pp_sorted[:10]:
    a, b = sorted(pair)
    print(f"  {c:>4}  {a}  <->  {b}")
worst_pair, worst_n = pp_sorted[0]
wa, wb = sorted(worst_pair)
total_bounces = sum(pingpong.values())
print(f"\nWorst ping-pong loop: {wa} <-> {wb} ({worst_n} bounce-backs)")
print(f"Total ping-pong bounces across all cases: {total_bounces}")
print(f"Cases with >=1 ping-pong bounce: "
      f"{sum(1 for p in team_path if any(p[i]==p[i+2] and p[i]!=p[i+1] for i in range(len(p)-2)))}")

# Q4  THE BOTTLENECK (longest waiting time per activity)
print("\n" + "=" * 70)
print("Q4  BOTTLENECK  (sojourn time per activity)")
print("=" * 70)
# Sojourn for event i = ts(i+1) - ts(i) within a case, attributed to activity(i).
df["next_ts"] = g[TS].shift(-1)
df["sojourn_h"] = (df["next_ts"] - df[TS]).dt.total_seconds() / 3600.0
soj = df.dropna(subset=["sojourn_h"])
agg = soj.groupby("activity")["sojourn_h"].agg(
    median_h="median", mean_h="mean", n="count")
agg["total_days"] = (soj.groupby("activity")["sojourn_h"].sum() / 24.0)
agg = agg.sort_values("median_h", ascending=False)
agg["median_d"] = agg["median_h"] / 24.0
print("Ranked by MEDIAN waiting time (top 13):")
print(agg[["median_h", "median_d", "mean_h", "total_days", "n"]].round(2).to_string())

# The Resolved/Closed sojourn is the administrative resolution->closure COOLDOWN
# (system waits before auto-closing), NOT an operational bottleneck. Exclude the
# terminal/admin states and rank the genuine operational waits.
ADMIN = {"Completed / Resolved", "Completed / Closed", "Completed / In Call",
         "Unmatched / Unmatched"}
oper = agg[~agg.index.isin(ADMIN)]
print("\nOperational waits only (excludes Resolved/Closed admin cooldown):")
print(oper[["median_h", "median_d", "total_days", "n"]].round(2).to_string())
top_med = oper.index[0]
top_total = oper["total_days"].idxmax()
print(f"\n#1 bottleneck by LONGEST single wait : '{top_med}' "
      f"(median {oper.loc[top_med,'median_h']:.1f} h)")
print(f"#1 bottleneck by TOTAL time lost     : '{top_total}' "
      f"({oper.loc[top_total,'total_days']:.0f} cumulative days, n={int(oper.loc[top_total,'n'])})")

# Q5  THE DRIVER (reassignments -> resolution time)
print("\n" + "=" * 70)
print("Q5  DRIVER  reassignments vs resolution time")
print("=" * 70)
dur_days = ((g[TS].max() - g[TS].min()).dt.total_seconds() / 86400.0)
drv = pd.DataFrame({"reassign": n_reassign, "days": dur_days}).dropna()
drv = drv[drv["days"] >= 0]

pear = stats.pearsonr(drv["reassign"], drv["days"])
spear = stats.spearmanr(drv["reassign"], drv["days"])
print(f"Pearson  r = {pear.statistic:.3f}  (p={pear.pvalue:.1e})")
print(f"Spearman r = {spear.statistic:.3f}  (p={spear.pvalue:.1e})")

drv["bucket"] = pd.cut(drv["reassign"], bins=[-1, 0, 1, 2, 100],
                       labels=["0", "1", "2", "3+"])
bk = drv.groupby("bucket", observed=True)["days"].agg(
    median_days="median", mean_days="mean", n="count")
base = bk.loc["0", "median_days"]
bk["x_vs_0"] = bk["median_days"] / base if base > 0 else np.nan
print("\nMedian resolution time by reassignment bucket:")
print(bk.round(2).to_string())
print(f"\nDefensible headline: each reassignment ladders resolution time UP "
      f"(0:{bk.loc['0','median_days']:.1f}d -> 1:{bk.loc['1','median_days']:.1f}d -> "
      f"2:{bk.loc['2','median_days']:.1f}d -> 3+:{bk.loc['3+','median_days']:.1f}d). "
      f"Spearman {spear.statistic:.2f}.")
print("(NB: the 0-bucket is near-instant 1st-line tickets, so a raw x-multiple vs 0 "
      "is baseline-inflated. Among reassigned tickets: 3+ vs 1 = "
      f"{bk.loc['3+','median_days']/bk.loc['1','median_days']:.1f}x.)")

# Control for complexity: does the reassignment ladder survive WITHIN each impact
# level? If yes, reassignment isn't just a proxy for hard tickets.
print("\nControlling for severity (impact) — median resolution days by impact x bucket:")
imp = df.groupby(CASE)["impact"].first()
drv2 = drv.join(imp.rename("impact"))
piv = drv2.pivot_table(index="impact", columns="bucket", values="days",
                       aggfunc="median", observed=True)
order = [x for x in ["Low", "Medium", "High", "Major"] if x in piv.index]
print(piv.reindex(order)[[c for c in ["0","1","2","3+"] if c in piv.columns]].round(2).to_string())
print("(Ladder rising left->right WITHIN each impact row = reassignment effect holds "
      "even at fixed severity.)")

# VISUALS
# Ping-pong chart (top pairs).
fig, ax = plt.subplots(figsize=(8, 4.5))
labels = [f"{sorted(p)[0]} <-> {sorted(p)[1]}" for p, _ in pp_sorted[:10]]
vals = [c for _, c in pp_sorted[:10]]
ax.barh(labels[::-1], vals[::-1], color="#C44E52")
ax.set_xlabel("Number of A->B->A bounce-backs")
ax.set_title("Q3 — Worst team ping-pong loops (reassignment bounce-backs)")
fig.tight_layout()
p1 = os.path.join(FIG_DIR, "03_pingpong.png")
fig.savefig(p1, dpi=130); plt.close(fig)
print(f"\nsaved: {p1}")

# Driver chart (median resolution time by bucket).
fig, ax = plt.subplots(figsize=(7, 4.5))
colors = ["#4C72B0", "#4C72B0", "#4C72B0", "#C44E52"]
bars = ax.bar(bk.index.astype(str), bk["median_days"], color=colors)
for b, v, x in zip(bars, bk["median_days"], bk["x_vs_0"]):
    ax.text(b.get_x()+b.get_width()/2, v, f"{v:.1f}d\n({x:.1f}x)",
            ha="center", va="bottom", fontsize=10)
ax.set_xlabel("Number of reassignments")
ax.set_ylabel("Median resolution time (days)")
ax.set_title("Q5 — More reassignments -> slower resolution")
ax.margins(y=0.18)
fig.tight_layout()
p2 = os.path.join(FIG_DIR, "03_driver_reassignments.png")
fig.savefig(p2, dpi=130); plt.close(fig)
print(f"saved: {p2}")
print("\nDONE.")
