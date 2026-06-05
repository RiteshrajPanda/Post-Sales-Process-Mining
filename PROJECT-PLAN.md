# Project Plan — After-Sales Service Process Mining

Working build plan derived from `after-sales-process-mining-brief.txt`.
Dataset locked: **BPI Challenge 2013 — Incidents log** (Volvo IT, VINST).
This doc is the contract for what the notebook must contain. Code happens next session.

---

## 0. Dataset decision (settled)

- **Use:** BPI Challenge 2013 — **_Incidents_** log (`.xes` / `.xes.gz`).
  - ~7,554 cases, ~65,533 events. Volvo IT Belgium incident management.
  - This is the log with reassignments + "push-to-front" ping-pong. The other two
    BPI13 logs (Open Problems, Closed Problems) do NOT carry the reassignment story — do not use them.
- **Source:** 4TU.ResearchData (DOI `10.4121/uuid:500573e6-accc-4b0c-9576-aa5468b10cee`),
  mirrored on the PM4Py / processmining.org dataset pages.
- **README honesty line (required):** "Public IT-service-desk log used as a stand-in for an
  appliance after-sales process — the event structure (ticket lifecycle, reassignments,
  reopens, SLA) is identical."

### The field that drives everything  ✅ VERIFIED against the real log (Evening 1)
Actual loaded shape: **65,533 events / 7,554 cases**, date range 2010-03-31 → 2012-05-23.

| XES field        | Meaning                                   | Used by |
|------------------|-------------------------------------------|---------|
| `case:concept:name` | SR Number (ticket id)                  | all     |
| `concept:name`   | **Status ONLY** — 4 values: `Accepted`, `Completed`, `Queued`, `Unmatched` | Q1, Q2 |
| `lifecycle:transition` | **Sub-status** — 13 values (the real detail, see below) | Q1, Q2, Q4 |
| `org:group`      | Support Team handling the ticket (e.g. `G97`, `V5 3rd`) — well populated | **Q3, Q5** |
| `org:resource`   | Individual owner (e.g. `Siebel`, `Frederic`)            | Q3      |
| `time:timestamp` | Event timestamp (UTC)                     | Q4, Q5  |
| `impact`         | Major / High / Medium / Low               | optional |
| also present     | `resource country`, `organization country`, `organization involved`, `org:role`, `product` | optional segmentation |

> ⚠️ **SCHEMA CORRECTION (important):** the plan originally assumed `concept:name`
> already combined Status+Sub-status. It does NOT — `concept:name` has only the 4
> top-level statuses. The sub-status lives in **`lifecycle:transition`**. So for the
> real analysis we build a **composite activity**:
> `activity = concept:name + " / " + lifecycle:transition`
> e.g. `Accepted / In Progress`, `Completed / Resolved`, `Queued / Awaiting Assignment`.
> The Evening-1 first map used the raw 4-state `concept:name` (fine as a sanity map);
> all KPI work from Evening 2 on uses the composite.

**Reassignment = a change in `org:group` between consecutive events of a case.**
Ping-pong = team A → team B → team A (or repeated bounce back to `Queued / Awaiting Assignment`).
The first map already shows it: `Accepted`→`Accepted` self-loop = 22,527, `Completed`→`Accepted` = 8,084.

### Activity vocabulary (verified counts)
- Statuses (`concept:name`): `Accepted` (40,117), `Completed` (13,867), `Queued` (11,544), `Unmatched` (5)
- Sub-statuses (`lifecycle:transition`): `In Progress` (30,239), `Awaiting Assignment` (11,544),
  `Resolved` (6,115), `Closed` (5,716), `Wait - User` (4,217), `Assigned` (3,221), `In Call` (2,035),
  `Wait` (1,533), `Wait - Implementation` (493), `Wait - Vendor` (313), `Wait - Customer` (101),
  `Unmatched` (5), `Cancelled` (1)
- **Ideal "happy path"** (reference model for Q1, using composite activity):
  `Accepted / In Progress` → `Completed / Resolved` → `Completed / Closed`

### Evening-1 observations that shape later analysis
- **Long parked tickets are real:** the very first sample case spans 2010→2012 with a
  ~2-year gap mid-case (a "Wait"/parked incident). Throughput-time will have a brutal long
  tail → report **median**, not mean, and consider a log-scale histogram (Q4/Q5).
- **`Siebel` is a system/bot resource** (6,162 events, far above any human) — likely automated
  status changes. Keep in mind when attributing rework to people (Q3).
- Ping-pong is visibly present in the sample case (V30 ↔ V5 3rd ↔ V13 2nd 3rd) → Q3 has a story.

---

## 1. After-sales translation layer (state once, reuse everywhere)

| IT-service-desk reality        | Appliance after-sales analog          |
|--------------------------------|---------------------------------------|
| `org:group` handover           | Ticket reassigned / wrong team / repeat technician dispatch |
| `Wait - User` / `Wait - Vendor`| Waiting on customer / waiting on spare parts |
| Resolved → reopened            | Repeat complaint, not first-time-fixed |
| Throughput time                | Resolution time vs SLA                 |
| Push-to-front / ping-pong      | Service bounce — cost with no progress |

Every chart caption ties the IT finding back to the after-sales analog. That tie-back is
what makes it read as analyst work, not a tutorial.

---

## 2. Notebook structure (one clean `.ipynb`, narrated)

`notebooks/after_sales_process_mining.ipynb`

1. **Title + framing** — what this is, the honesty line, the translation table above.
2. **Load & inspect** — read XES, basic shape, column inventory, date range, event-name counts.
3. **Q1 — Happy-path conformance**
4. **Q2 — First-time-fix / reopen rate**
5. **Q3 — Biggest rework loop (ping-pong)**
6. **Q4 — The bottleneck (longest wait)**
7. **Q5 — One driver (reassignments → resolution time)**
8. **Findings** — the 3 punchy bullets with real numbers, mirrored into the README.

Each analysis section = short markdown setup → code → one number/chart → one-sentence
after-sales interpretation.

---

## 3. The five analyses — exact approach

### Q1. Happy-path conformance
- Discover the real process map: `pm4py.discover_directly_follows_graph(log)` and an
  inductive model `pm4py.discover_petri_net_inductive(log)` for the visual.
- Get variants: `pm4py.get_variants(log)`; sort by frequency.
- Define the ideal trace = `Accepted/In Progress → Completed/Resolved → Completed/Closed`.
- **Output:** % of cases on the clean path vs % that detour. Bar/Pareto of top variants.
- *Risk:* exact-match happy path may be tiny (real logs are messy). Fallback metric:
  "% of cases that never revisit an active state after first Resolved" — softer but honest.

### Q2. First-time-fix / reopen rate
- Reopen = a case reaches a `Completed/Resolved` (or `Closed`) event and then has a LATER
  event that returns to an active state (`Accepted/In Progress`, `Queued/*`).
- Compute per-case with pandas groupby on sorted timestamps.
- **Output:** reopen rate % = first-time-fix-rate complement. Single headline number.

### Q3. Biggest rework loop (ping-pong)
- Per case, build the sequence of `org:group` values; collapse consecutive duplicates.
- Count handovers (length of collapsed sequence − 1) and detect A→B→A bounces.
- Aggregate: which (team A ↔ team B) pair appears most / wastes most time.
- Use `pm4py.discover_performance_dfg` on an `org:group`-as-activity view to get time on edges.
- **Output:** the single worst ping-pong loop + how much cumulative time it burns. Chart:
  top reassignment loops by frequency or by total wasted hours.

### Q4. The bottleneck (longest waiting time)
- `pm4py.discover_performance_dfg(log)` → per-activity sojourn / per-edge waiting time.
  Or `pm4py.get_all_case_durations` + per-activity sojourn via `soj_time` stats.
- Rank activities by median waiting time. Expect `Wait - User` and
  `Queued/Awaiting Assignment` near the top.
- **Output:** ranked bar of mean/median wait per step. Name the #1 bottleneck and its analog
  ("waiting on customer / parts").

### Q5. One driver (diagnostic — the resume-bullet engine)
- Per case: `n_reassignments` (= `org:group` changes) and `throughput_time` (last − first ts).
- Correlation (`scipy.stats.pearsonr` / `spearmanr`) + simple regression (`numpy.polyfit` or
  `statsmodels.OLS`).
- **Find the threshold:** bucket by reassignment count (0, 1, 2, 3+), report median resolution
  time per bucket → "3+ reassignments took Nx longer."
- **Output:** scatter or bucketed bar with the multiplier called out. This is the bullet:
  *"Tickets reassigned 3+ times took [N]x longer to resolve — reassignment, not complexity,
  drove the slow tail."*

---

## 4. Deliverables (tight)

- `notebooks/after_sales_process_mining.ipynb` — narrated, runs top-to-bottom clean.
- **3–4 visuals**, saved to `figures/`:
  1. discovered process map
  2. throughput-time histogram
  3. ping-pong / rework chart
  4. one driver chart (Q5)
- `README.md` — 1 page, the honesty framing + **3 findings as resume bullets with numbers**.
- `requirements.txt` — pinned: `pm4py`, `pandas`, `matplotlib`, `scipy`, `jupyter` (+ `statsmodels` if used).
- Push to GitHub. Repo link → cold email + resume.

### Repo layout (to create next session)
```
.
├─ after-sales-process-mining-brief.txt   (the brief — keep)
├─ PROJECT-PLAN.md                          (this file)
├─ README.md                                (write last, with real numbers)
├─ requirements.txt
├─ data/                                     (raw .xes — likely .gitignored if large)
├─ notebooks/
│   └─ after_sales_process_mining.ipynb
└─ figures/
```

---

## 5. Build sequence (the 4 evenings, mapped to concrete exits)

- **Evening 1 — Setup & load.** venv + `requirements.txt`; download Incidents `.xes`;
  `read_xes`; column inventory; first process map. *Exit:* map renders, columns understood.
- **Evening 2 — KPIs.** Q1 happy-path %, Q2 reopen rate, throughput-time distribution.
  *Exit:* three numbers on the board.
- **Evening 3 — Loops + driver + visuals.** Q3 ping-pong, Q4 bottleneck, Q5 driver;
  build the 4 figures. *Exit:* all charts saved to `figures/`.
- **Evening 4 — Write & ship.** 3 findings, README, push to GitHub, draft the email line.
  *Exit:* public repo link in hand.

---

## Evening 2 — VERIFIED RESULTS (the first three KPIs)

Composite activity = `concept:name / lifecycle:transition` → **13 activities**.

**Q1 — Happy-path conformance**
- Exact match to ideal `In Progress → Resolved → Closed`: **0.0%** (as predicted — real
  cases always repeat `In Progress` or pass through `Queued` first). Lead with the soft metric.
- **2,278 distinct variants** across 7,554 cases — high process variability.
- Top variant (**23.2%**, 1,749 cases): `In Progress → In Progress → Completed / In Call`
  — note it ends at **In Call**, not a formal resolution.
- **Soft conformance (ends Completed, never reopened): 93.1%.**

**Key judgment call — `Completed` ≠ `Resolved`.** The `Completed` status also covers
`In Call` (agent on a phone = mid-work). Genuine resolution = sub-status `Resolved`/`Closed`.
- **25.0% of tickets (1,891) NEVER reach Resolved/Closed** — they end in In Call / Wait /
  Queued. Either resolved-on-call without proper closure (process-compliance / data-hygiene
  gap) or abandoned. **Strong candidate finding.**

**Q2 — Reopen rate / first-time-fix**
- Loose (any Completed → back to active): **6.8%** reopened.
- Strict (after Resolved/Closed → returns to work): **5.2%** of all cases;
  **6.9% of the 5,663 resolved cases** ← the defensible FTF denominator.
- First-time-fix rate ≈ **93–95%** depending on definition.
- Reopen-count tail: 460 cases bounced back once, 46 twice, a few 3–6×.

**Throughput-time distribution**
- median **7.5 days**, mean **12.1 days** (1.6× median), p95 **35.7d**, p99 **116.6d**, max **771d**.
- Distribution is **bimodal** (log scale): a near-instant cluster (~minutes, likely auto/trivial)
  + the main ~1-week hump. Report median; show the log-scale histogram.
- Figure: `figures/02_throughput_histogram.png`.

> ✅ DECIDED: headline reopen number = **6.9% of resolved cases** (cleanest denominator).
> Which finding *opens* the README is still TBD (revisit after Evening 3).

## Evening 3 — VERIFIED RESULTS (loops, bottleneck, driver)

**Q3 — Ping-pong (org:group handovers)** — `org:group` has 0 nulls, 649 distinct teams.
- Reassignments/case: mean 1.25, median 1, max 31. 3,734 cases (49%) never reassigned.
- **1,177 cases (15.6%) have ≥1 ping-pong bounce** (A→B→A); 2,394 bounces total.
- Worst loop: **`D8 ↔ V37 2nd` (84 bounce-backs)**. Top directed handover: `G96 → G97` (255).
- Figure: `figures/03_pingpong.png`.

**Q4 — Bottleneck** — ⚠️ raw #1 was `Completed / Resolved` (176 h) but that's the
**administrative Resolved→Closed cooldown**, not an operational wait — excluded it.
- Operational bottleneck by **longest single wait**: `Wait - Customer` (median 54.4 h / 2.3 d).
- Operational bottleneck by **total time lost**: `Wait - User` (**19,312 cumulative days**, n=4,214)
  — waiting on the customer/user is where the most aggregate time leaks. `Wait - Vendor`
  (1.2 d, the parts analog) is next. **Queue assignment is NOT the bottleneck** (median 0.6 h).
- After-sales map: Wait-User/Customer = waiting on customer access/info; Wait-Vendor = waiting on parts.

**Q5 — Driver (reassignments → resolution time)** — THE resume bullet.
- Pearson r = 0.329; **Spearman r = 0.557 (p≈0)** — strong monotonic association.
- Median resolution by bucket: 0:**0.3 d** → 1:**8.4 d** → 2:**10.0 d** → 3+:**13.9 d** (clean ladder).
- ⚠️ The raw "47× vs 0" is baseline-inflated (0-bucket = near-instant 1st-line tickets).
  Defensible framings: the monotonic ladder + Spearman 0.56; among *reassigned* tickets 3+ vs 1 = 1.6×.
- **Controlled for severity (impact):** ladder still rises within every impact level
  (e.g. High: 7.4→8.1→8.4→11.2 d) → reassignment effect holds at fixed complexity,
  so it's **not merely a complexity proxy**. This is what makes the bullet defensible.
- Figure: `figures/03_driver_reassignments.png`.

### Candidate headline findings (pick 3 for the README)
1. **6.9% of resolved tickets were reopened** (not first-time-fixed); reopen tail up to 6×.
2. **1 in 4 tickets never gets a formal Resolved/Closed** — closed-on-call or abandoned (process-compliance gap).
3. **Reassignment drives the slow tail**: 3+ reassignments → 13.9-day median vs 0.3 d; ladder holds even within severity (Spearman 0.56).
4. **15.6% of tickets ping-pong between teams**; worst loop D8↔V37 2nd bounced 84×.
5. **Waiting on the customer/user is the top operational delay** (19,312 cumulative days lost), not queue assignment.

## 6. Known risks / decisions to make while building
- **Exact happy-path match may be ~0%** → use the softer "no reopen after resolve" framing (noted in Q1).
- **XES load size/time** → if `.xes` is slow, use `.xes.gz` directly; PM4Py reads gzipped.
- **`org:group` blanks** → some events lack a team; decide forward-fill vs drop before counting reassignments. Document the choice.
- **Activity granularity** → if Status+Sub-status makes too many activities, optionally analyze on Status only for the map, keep full granularity for KPIs.
- **statsmodels optional** → numpy/scipy is enough for Q5; only add statsmodels if we want a clean OLS summary table.
```
