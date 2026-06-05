"""
Evening 2 — composite activity + the first three KPIs:
  Q1  happy-path conformance (exact match vs the soft "no reopen" metric)
  Q2  reopen rate  ->  first-time-fix rate
  +   throughput-time distribution (median, percentiles, log-scale histogram)

Scratch/validation script; narrated logic moves into the notebook later.
All KPI logic is plain pandas (transparent + defensible); pm4py only renders.
"""
import os
import numpy as np
import pandas as pd
import pm4py

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 160)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(BASE, "data", "BPI_Challenge_2013_incidents.xes.gz")
FIG_DIR = os.path.join(BASE, "figures")
os.makedirs(FIG_DIR, exist_ok=True)

gv_bin = r"C:\Program Files\Graphviz\bin"
if os.path.isdir(gv_bin) and gv_bin not in os.environ.get("PATH", ""):
    os.environ["PATH"] += os.pathsep + gv_bin

CASE = "case:concept:name"
STATUS = "concept:name"          # Accepted / Completed / Queued / Unmatched
SUB = "lifecycle:transition"     # In Progress / Resolved / Closed / ...
TS = "time:timestamp"

# ----------------------------------------------------------------------
# Load + build composite activity, preserving the XES trace order.
# ----------------------------------------------------------------------
df = pm4py.read_xes(LOG_PATH)
df = df.reset_index(drop=True)
df["evt_order"] = df.index                      # stable original order within the file
df["activity"] = df[STATUS].astype(str) + " / " + df[SUB].astype(str)

# Confirm trace order is sane: events come grouped by case, time mostly increasing.
print(f"events={len(df):,}  cases={df[CASE].nunique():,}  activities={df['activity'].nunique()}")
print("\nTop composite activities:")
print(df["activity"].value_counts().head(12))

# ----------------------------------------------------------------------
# Per-case sequences (in trace order).
# ----------------------------------------------------------------------
g = df.groupby(CASE, sort=False)
seq_status = g[STATUS].apply(list)              # ordered list of statuses per case
seq_activity = g["activity"].apply(list)        # ordered list of composite activities
ts_min = g[TS].min()
ts_max = g[TS].max()
n_cases = len(seq_status)

# ======================================================================
# Q1  HAPPY-PATH CONFORMANCE
# ======================================================================
print("\n" + "=" * 70)
print("Q1  HAPPY-PATH CONFORMANCE")
print("=" * 70)

IDEAL = ("Accepted / In Progress", "Completed / Resolved", "Completed / Closed")
variant_counts = seq_activity.apply(tuple).value_counts()
exact = int(variant_counts.get(IDEAL, 0))
print(f"Ideal happy path: {' -> '.join(IDEAL)}")
print(f"Exact-match cases: {exact:,} / {n_cases:,} = {exact / n_cases:.1%}")

print(f"\nDistinct variants (unique paths): {variant_counts.size:,}")
print("Top 10 variants by frequency:")
for i, (v, c) in enumerate(variant_counts.head(10).items(), 1):
    print(f"  {i:>2}. {c:>5} ({c / n_cases:5.1%})  {' -> '.join(v)}")

# Soft conformance: a case is "clean" if it ends Completed AND never returns to
# an active state (Accepted/Queued) after first reaching Completed.
def is_reopened(statuses):
    seen_completed = False
    for s in statuses:
        if s == "Completed":
            seen_completed = True
        elif seen_completed and s in ("Accepted", "Queued"):
            return True
    return False

reopened = seq_status.apply(is_reopened)
ends_completed = seq_status.apply(lambda s: s[-1] == "Completed")
clean = ends_completed & ~reopened
print(f"\nSoft conformance (ends Completed & never reopened): "
      f"{int(clean.sum()):,} / {n_cases:,} = {clean.mean():.1%}")

# ======================================================================
# Q2  REOPEN RATE  ->  FIRST-TIME-FIX RATE
# ======================================================================
print("\n" + "=" * 70)
print("Q2  REOPEN RATE / FIRST-TIME-FIX")
print("=" * 70)
reopen_rate = reopened.mean()
print(f"Reopened (Completed then back to Accepted/Queued): "
      f"{int(reopened.sum()):,} / {n_cases:,} = {reopen_rate:.1%}")
print(f"First-time-fix rate (complement):                 {1 - reopen_rate:.1%}")

# How many times do reopened cases bounce back?
def reopen_count(statuses):
    n, seen = 0, False
    for s in statuses:
        if s == "Completed":
            seen = True
        elif seen and s in ("Accepted", "Queued"):
            n += 1
            seen = False
    return n

reopen_n = seq_status.apply(reopen_count)
print("\nReopen-count distribution (how many times a case bounced back):")
print(reopen_n.value_counts().sort_index().head(10).to_string())

# ======================================================================
# THROUGHPUT-TIME DISTRIBUTION
# ======================================================================
print("\n" + "=" * 70)
print("THROUGHPUT-TIME DISTRIBUTION (case duration)")
print("=" * 70)
dur_days = (ts_max - ts_min).dt.total_seconds() / 86400.0
q = dur_days.quantile([0.25, 0.5, 0.75, 0.90, 0.95, 0.99])
print(f"mean   : {dur_days.mean():8.1f} days   <- skewed up by the long tail")
print(f"median : {q[0.50]:8.1f} days   <- the typical ticket")
print(f"p25    : {q[0.25]:8.1f} days")
print(f"p75    : {q[0.75]:8.1f} days")
print(f"p90    : {q[0.90]:8.1f} days")
print(f"p95    : {q[0.95]:8.1f} days")
print(f"p99    : {q[0.99]:8.1f} days")
print(f"max    : {dur_days.max():8.1f} days")
print(f"\nMean/median ratio: {dur_days.mean() / q[0.50]:.1f}x  "
      f"(why we report median, not mean)")

# ======================================================================
# REFINEMENT — "Completed" != "Resolved".  The status `Completed` also covers
# `In Call` (agent on a phone call = mid-work, not a fix). The genuine
# resolution markers are the sub-statuses Resolved / Closed. Recompute Q1/Q2
# against that stricter, more defensible definition.
# ======================================================================
print("\n" + "=" * 70)
print("REFINEMENT  resolution = sub-status in {Resolved, Closed} only")
print("=" * 70)

RESOLVED = {"Resolved", "Closed"}
seq_sub = g[SUB].apply(list)

def ever_resolved(subs):
    return any(s in RESOLVED for s in subs)

def reopened_strict(subs):
    """After the FIRST Resolved/Closed, does the case return to real work?"""
    seen = False
    for s in subs:
        if s in RESOLVED:
            seen = True
        elif seen and s in ("In Progress", "Awaiting Assignment", "Assigned",
                            "In Call", "Wait - User", "Wait", "Wait - Implementation",
                            "Wait - Vendor", "Wait - Customer"):
            return True
    return False

resolved_flag = seq_sub.apply(ever_resolved)
never_resolved = ~resolved_flag
reopened_v2 = seq_sub.apply(reopened_strict)

print(f"Cases that NEVER reach Resolved/Closed: "
      f"{int(never_resolved.sum()):,} / {n_cases:,} = {never_resolved.mean():.1%}")
print(f"  (these end in In Call / Wait / Queued — closed without formal resolution)")
print(f"\nReopen rate, strict (reopened after Resolved/Closed):")
print(f"  of ALL cases        : {int(reopened_v2.sum()):,} / {n_cases:,} = {reopened_v2.mean():.1%}")
resolved_n = int(resolved_flag.sum())
print(f"  of RESOLVED cases   : {int(reopened_v2.sum()):,} / {resolved_n:,} = "
      f"{reopened_v2.sum() / resolved_n:.1%}   <- true first-time-fix denominator")
print(f"\nDefinition comparison for the reopen rate:")
print(f"  loose  (any Completed -> active) : {reopen_rate:.1%}")
print(f"  strict (Resolved/Closed -> work) : {reopened_v2.mean():.1%}")

# Log-scale histogram of throughput time.
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

pos = dur_days[dur_days > 0]
fig, ax = plt.subplots(figsize=(8, 4.5))
bins = np.logspace(np.log10(pos.min()), np.log10(pos.max()), 40)
ax.hist(pos, bins=bins, color="#4C72B0", edgecolor="white")
ax.set_xscale("log")
ax.axvline(q[0.50], color="#C44E52", linestyle="--", linewidth=2,
           label=f"median {q[0.50]:.1f}d")
ax.axvline(dur_days.mean(), color="#55A868", linestyle="--", linewidth=2,
           label=f"mean {dur_days.mean():.1f}d")
ax.set_xlabel("Resolution time (days, log scale)")
ax.set_ylabel("Number of tickets")
ax.set_title("Throughput-time distribution — long right tail")
ax.legend()
fig.tight_layout()
out = os.path.join(FIG_DIR, "02_throughput_histogram.png")
fig.savefig(out, dpi=130)
print(f"\nsaved: {out}")
print("\nDONE.")
