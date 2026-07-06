# Simulation & Coverage Analysis

Tools for stress-testing judge coverage before a live event.

## Quick start

Run a 2-hour simulation and see which projects go unseen:

```bash
python coverage.py --time 120
```

---

## simulate.py

Drives synthetic votes for all active judges using real DB data. Vote outcomes use a Bradley-Terry weighted coin flip based on current project scores.

```bash
python simulate.py                  # 2-hour window, 3-5 min demos, 2-3 min walks
python simulate.py --time 90        # custom time window (minutes)
python simulate.py --no-time-limit  # run every judge to full exhaustion
python simulate.py --reset          # wipe all simulation data and restore priors
```

Timing flags (can be combined with any of the above):

```bash
python simulate.py --time 120 --demo-min 3 --demo-max 5 --walk-min 2 --walk-max 3
```

---

## coverage.py

Analyzes judge/project ratios and unseen projects per pool.

```bash
# Analyze existing simulation data
python coverage.py

# Reset, run a fresh sim, then analyze
python coverage.py --time 120

# Show judge/project/factor per pool without running a simulation
python coverage.py --pools

# Add recommended judges temporarily, simulate, and show if gaps are fixed
python coverage.py --what-if

# Find the minimum judge count per pool that guarantees 0 unseen across N runs
python coverage.py --guarantee
python coverage.py --guarantee --trials 20   # more runs = more confidence
```

### Reading the output

| Column | Meaning |
|--------|---------|
| Judges | Judges assigned to this pool |
| Projects | Active projects in this pool |
| Unseen | Projects with zero visits in this simulation run |
| Need | Minimum judges for theoretical full coverage (`ceil(projects / projects_per_judge)`) |
| Gap | How many judges short of the minimum you are |
| Factor | `(judges × projects_per_judge) / projects` — aim for 2x+ |

**thin** = enough judges by the formula but randomness still left some projects unseen.

### Factor explained

`projects_per_judge` = how many projects a judge can visit in the time window:

```
projects_per_judge = time_budget / (avg_demo + avg_walk)
                   = 120 / (4 + 2.5) ≈ 18
```

Factor = total visits possible / total projects. A factor of 1.0 means you have exactly enough capacity for one visit per project with zero overlap — which never happens in practice. Aim for 2x+ to absorb random clustering.

---

## Common workflows

**Check pool staffing before the event (no simulation needed):**
```bash
python coverage.py --pools
```

**Run a single simulation and check results:**
```bash
python simulate.py --reset && python simulate.py --time 120
python coverage.py
```

**Find how many judges you'd need to guarantee full coverage:**
```bash
python coverage.py --guarantee --time 120 --trials 10
```
