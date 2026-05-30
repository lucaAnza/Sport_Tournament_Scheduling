#!/usr/bin/env python3

import argparse
import json
import time
from pathlib import Path

from mip import (
    Model,
    BINARY,
    INTEGER,
    CBC,
    xsum,
    minimize,
    OptimizationStatus,
)


# ============================================================
# 1. ARGUMENT PARSING AND PATHS
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="MIP model for the Sports Tournament Scheduling problem."
    )

    parser.add_argument(
        "n",
        type=int,
        help="Number of teams. Must be even."
    )

    parser.add_argument(
        "--optimized",
        "--optimization",
        "--opt",
        action="store_true",
        help="Run the optional optimization version balancing home/away games."
    )

    parser.add_argument(
        "--docker",
        action="store_true",
        help="Write output to /app/outputs/MIP, used inside Docker."
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Optional custom output directory."
    )

    return parser.parse_args()


def find_project_root():

    current_file = Path(__file__).resolve()

    for parent in current_file.parents:
        if parent.name == "code":
            return parent.parent

    
    return current_file.parent.parent


def get_output_directory(args):
    if args.output_dir is not None:
        return Path(args.output_dir).resolve()

    if args.docker:
        return Path("/app/outputs/MIP")

    project_root = find_project_root()
    return project_root / "res" / "MIP"


# ============================================================
# 2. JSON UTILITIES
# ============================================================

def load_json_file(filename):
    if not filename.exists():
        return {}

    with open(filename, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Invalid JSON format in {filename}: expected object.")

    return data


def save_json_file(filename, data):
    filename.parent.mkdir(parents=True, exist_ok=True)

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def add_solution_json(data, approach_name, runtime, optimal, obj, sol):
    data[approach_name] = {
        "time": runtime,
        "optimal": optimal,
        "obj": obj,
        "sol": sol,
    }

    return data


# ============================================================
# 3. INSTANCE SETUP
# ============================================================

args = parse_args()

n = args.n
W = n - 1
P = n // 2
TIME_LIMIT = 300
SOLVER_TIME_LIMIT = 299

output_dir = get_output_directory(args)
output_file = output_dir / f"{n}.json"

if n < 2:
    raise ValueError("Invalid STS instance: n must be at least 2.")

if n % 2 != 0:
    raise ValueError(
        "Invalid STS instance: n must be even because each week has n/2 games."
    )

teams = range(n)
weeks = range(W)
periods = range(P)

pairs = []

for i in teams:
    for j in teams:
        if i < j:
            pairs.append((i, j))

number_of_pairs = len(pairs)

if W * P != number_of_pairs:
    raise ValueError(
        f"Invalid STS instance: W * P must equal n(n-1)/2. "
        f"Got W * P = {W * P}, but number of pairs = {number_of_pairs}."
    )

pair_idx = {}

for k, pair in enumerate(pairs):
    pair_idx[pair] = k


# ============================================================
# 4. CREATE MODEL
# ============================================================

model_build_start = time.perf_counter()

m = Model(sense=minimize, solver_name=CBC)
m.verbose = 0
m.threads = 1

# ============================================================
# 5. DECISION VARIABLES
# ============================================================

# y[w][p][k] = 1 iff pair k is scheduled in week w and period p.
y = []

for w in weeks:
    week_vars = []

    for p in periods:
        period_vars = []

        for k in range(number_of_pairs):
            period_vars.append(m.add_var(var_type=BINARY))

        week_vars.append(period_vars)

    y.append(week_vars)


# home[w][p][k] decides the orientation of pair k if selected:
# pair k = (i, j), i < j
# home = 1 means i is home and j is away.
# home = 0 means j is home and i is away.
home = []

for w in weeks:
    week_vars = []

    for p in periods:
        period_vars = []

        for k in range(number_of_pairs):
            period_vars.append(m.add_var(var_type=BINARY))

        week_vars.append(period_vars)

    home.append(week_vars)


# ============================================================
# 6. CORE STS CONSTRAINTS
# ============================================================

# Every pair of teams plays exactly once.
for k in range(number_of_pairs):
    m += xsum(y[w][p][k] for w in weeks for p in periods) == 1


# Each week-period slot hosts exactly one game.
for w in weeks:
    for p in periods:
        m += xsum(y[w][p][k] for k in range(number_of_pairs)) == 1


# Every team plays exactly once per week.
for w in weeks:
    for t in teams:
        m += xsum(y[w][p][k] for p in periods for k, (i, j) in enumerate(pairs) if t == i or t == j) == 1


# Every team plays at most twice in the same period across the tournament.
for t in teams:
    for p in periods:
        m += xsum(y[w][p][k] for w in weeks for k, (i, j) in enumerate(pairs) if t == i or t == j) <= 2


# ============================================================
# 7. HOME/AWAY LINKING CONSTRAINTS
# ============================================================

# If pair k is not selected in slot (w, p), then home[w][p][k] must be 0.
# If pair k is selected, home[w][p][k] can be 0 or 1.
for w in weeks:
    for p in periods:
        for k in range(number_of_pairs):
            m += home[w][p][k] <= y[w][p][k]


# ============================================================
# 8. SAFE SYMMETRY BREAKING
# ============================================================

# Fix the first week:
# period 0 -> team 0 vs team 1
# period 1 -> team 2 vs team 3
# etc.
for p in periods:
    fixed_home_team = 2 * p
    fixed_away_team = 2 * p + 1

    fixed_pair = (fixed_home_team, fixed_away_team)
    fixed_pair_index = pair_idx[fixed_pair]

    m += y[0][p][fixed_pair_index] == 1
    m += home[0][p][fixed_pair_index] == 1


# Fix team 0's opponent by week:
# week 0 -> team 0 plays team 1
# week 1 -> team 0 plays team 2
# ...
# week n-2 -> team 0 plays team n-1
for w in weeks:
    opponent = w + 1

    fixed_pair = (0, opponent)
    fixed_pair_index = pair_idx[fixed_pair]

    m += xsum(y[w][p][fixed_pair_index] for p in periods) == 1



for p in periods:
    terms = []

    for k in range(number_of_pairs):
        pair = pairs[k]
        i = pair[0]

        if i == 0:
            terms.append(y[p][p][k])

    m += xsum(terms) == 1



# ============================================================
# 9. DECISION MODE VS OPTIMIZATION MODE
# ============================================================

if args.optimized:
    solution_name = "mip_cbc_optimization"

    home_cnt = []

    for t in teams:
        home_cnt.append(m.add_var(var_type=INTEGER, lb=0, ub=W))

    for t in teams:
        home_terms = []

        for w in weeks:
            for p in periods:
                for k, (i, j) in enumerate(pairs):
                    if t == i:
                        # If i is the home team.
                        home_terms.append(home[w][p][k])

                    elif t == j:
                        # If j is the home team.
                        # Since pair is selected iff y = 1:
                        # home = 0 means j is home.
                        home_terms.append(y[w][p][k] - home[w][p][k])

        m += home_cnt[t] == xsum(home_terms)

    balance = []

    for t in teams:
        # Since W = n - 1 and n is even, W is odd.
        # Therefore the best possible imbalance is at least 1.
        balance.append(m.add_var(var_type=INTEGER, lb=W % 2, ub=W))

    for t in teams:
        away_cnt = W - home_cnt[t]

        # balance[t] >= |home_cnt[t] - away_cnt|
        m += balance[t] >= home_cnt[t] - away_cnt
        m += balance[t] >= away_cnt - home_cnt[t]

    m.objective = xsum(balance[t] for t in teams)

    m.max_mip_gap = 0.0

else:
    solution_name = "mip_cbc_decision"

    # Dummy zero objective for feasibility version.
    m.objective = xsum([])


# ============================================================
# 10. SOLVE
# ============================================================

solve_start = time.perf_counter()
status = m.optimize(max_seconds=SOLVER_TIME_LIMIT)
solve_end = time.perf_counter()

# Reports total runtime, including model construction time.
total_runtime = solve_end - model_build_start
runtime_floor = int(total_runtime)

has_solution = m.num_solutions > 0


# ============================================================
# 11. BUILD SOLUTION MATRIX
# ============================================================

def extract_schedule():
    schedule = []

    for p in periods:
        row = []

        for w in weeks:
            row.append(None)

        schedule.append(row)

    for w in weeks:
        for p in periods:
            for k, (i, j) in enumerate(pairs):
                if y[w][p][k].x is not None and y[w][p][k].x >= 0.99:
                    if home[w][p][k].x is not None and home[w][p][k].x >= 0.5:
                        schedule[p][w] = [i + 1, j + 1]
                    else:
                        schedule[p][w] = [j + 1, i + 1]

    return schedule


# ============================================================
# 12. INTERPRET STATUS AND EXPORT
# ============================================================

data = load_json_file(output_file)

solved_runtime_to_export = min(runtime_floor, TIME_LIMIT - 1)

if args.optimized:
    optimal = status == OptimizationStatus.OPTIMAL

    if has_solution:
        sol_to_export = extract_schedule()
        obj_to_export = int(round(m.objective_value))

        if optimal:
            runtime_to_export = solved_runtime_to_export
        else:
            runtime_to_export = TIME_LIMIT

    else:
        sol_to_export = []
        obj_to_export = None
        optimal = False
        runtime_to_export = TIME_LIMIT

else:
    if has_solution:
        sol_to_export = extract_schedule()
        obj_to_export = None
        optimal = True
        runtime_to_export = solved_runtime_to_export

    else:
        sol_to_export = []
        obj_to_export = None
        optimal = False
        runtime_to_export = TIME_LIMIT


data = add_solution_json(
    data=data,
    approach_name=solution_name,
    runtime=runtime_to_export,
    optimal=optimal,
    obj=obj_to_export,
    sol=sol_to_export,
)

save_json_file(output_file, data)


# ============================================================
# 13. CONSOLE OUTPUT
# ============================================================

print("======================================")
print("MIP finished")
print("======================================")
print(f"Instance n: {n}")
print(f"Mode: {'optimization' if args.optimized else 'decision'}")
print(f"Solver: CBC")
print(f"Status: {status}")
print(f"Solutions found: {m.num_solutions}")
print(f"Runtime floor: {runtime_floor}")
print(f"Exported time: {runtime_to_export}")
print(f"Optimal exported: {optimal}")
print(f"Objective exported: {obj_to_export}")
print(f"Output file: {output_file}")
print("======================================")
