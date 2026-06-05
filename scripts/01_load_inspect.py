"""
Evening 1 — load the BPI Challenge 2013 Incidents log, inventory the columns,
and render the first process map. This is the scratch/validation script; the
narrated logic moves into notebooks/ next session.
"""
import os
import pm4py
import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 160)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(BASE, "data", "BPI_Challenge_2013_incidents.xes.gz")
FIG_DIR = os.path.join(BASE, "figures")
os.makedirs(FIG_DIR, exist_ok=True)

# Make sure Graphviz is reachable for rendering even if PATH isn't refreshed.
gv_bin = r"C:\Program Files\Graphviz\bin"
if os.path.isdir(gv_bin) and gv_bin not in os.environ.get("PATH", ""):
    os.environ["PATH"] += os.pathsep + gv_bin

print("=" * 70)
print("LOADING:", LOG_PATH)
print("=" * 70)

# pm4py reads gzipped XES directly. Returns a flattened DataFrame.
df = pm4py.read_xes(LOG_PATH)

print("\n--- SHAPE ---")
print(f"events (rows): {len(df):,}")
print(f"cases        : {df['case:concept:name'].nunique():,}")
print(f"activities   : {df['concept:name'].nunique()}")

print("\n--- COLUMNS ---")
for c in df.columns:
    print(f"  {c:<30} dtype={df[c].dtype}")

print("\n--- DATE RANGE ---")
print("from:", df["time:timestamp"].min())
print("to  :", df["time:timestamp"].max())

print("\n--- ACTIVITY (concept:name) value counts ---")
print(df["concept:name"].value_counts())

for col in ["org:group", "org:resource", "impact", "lifecycle:transition"]:
    if col in df.columns:
        print(f"\n--- {col} value counts (top 15) ---")
        print(df[col].value_counts(dropna=False).head(15))

print("\n--- SAMPLE: one full case, sorted by time ---")
first_case = df.sort_values("time:timestamp")["case:concept:name"].iloc[0]
cols = [c for c in ["case:concept:name", "concept:name", "org:group",
                    "org:resource", "time:timestamp"] if c in df.columns]
print(df[df["case:concept:name"] == first_case][cols].sort_values("time:timestamp").to_string(index=False))

print("\n" + "=" * 70)
print("RENDERING FIRST PROCESS MAP (DFG)")
print("=" * 70)
dfg, start, end = pm4py.discover_dfg(df)
map_path = os.path.join(FIG_DIR, "01_first_process_map_dfg.png")
pm4py.save_vis_dfg(dfg, start, end, map_path)
print("saved:", map_path)

print("\nDONE.")
