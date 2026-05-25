import time
import sys
from mip import Model, BINARY, INTEGER, xsum, minimize, OptimizationStatus
from common.utils import *




# ========== SETTINGS VARIABLE ========== #
script_path = ''
docker_path = '/app/outputs/MIP/'
debug_info = False

# ==================================== problem size ====================================
n , W , P , _ , default_filename , opt_enable , _ = get_user_settings(sys.argv , docker_path , script_path)
teams = range(n)
weeks = range(W)
periods = range(P)

pairs = [(i, j) for i in teams for j in teams if i < j] # all ordered pairs (i<j) (to avoid double match-ups)
pair_idx = {(i, j): k for k, (i, j) in enumerate(pairs)} # Precompute pair -> index (fast lookup)

solution_name = f'MIP'
# ==================================== MODEL and VARIABLES ====================================
# the model aim is to minimize the objective function
m = Model(sense=minimize)
m.verbose = 0  # Avoid to print a lot of information about solving

# y[w][p][i,j] = 1 if match (i,j) is placed in week w, period p
y = [[[m.add_var(var_type=BINARY) for _ in pairs] for _ in periods] for _ in weeks]

# home[w][p][i,j] = 1 if    i is home vs j in (w,p)
# we just have one home-variable for each match:
# i is the team with the lowest index and plays home if home[w][p][i,j]=1
home = [[[m.add_var(var_type=BINARY) for _ in pairs] for _ in periods] for _ in weeks]


# ==================================== constraints ====================================

# 1) Every pair plays exactly once (some week & period)
for k, (i, j) in enumerate(pairs):
    m += xsum(y[w][p][k] for w in weeks for p in periods) == 1

# 2) Each (week,period) hosts exactly one game
for w in weeks:
    for p in periods:
        m += xsum(y[w][p][k] for k in range(len(pairs))) == 1

# 3) Every team plays exactly once per week
for w in weeks:
    for t in teams:
        m += xsum(
            y[w][p][k]
            for p in periods
            for k, (i, j) in enumerate(pairs)
            if t in (i, j)
        ) == 1

# 4) no team appears more than twice in the same period across the season
for t in teams:
    for p in periods:
        m += xsum(
            y[w][p][k]
            for w in weeks
            for k, (i, j) in enumerate(pairs)
            if t in (i, j)
        ) <= 2

# ==================================== Home/Away tying and objective ====================================
# Link home to y: for each placed game (i,j) in (w,p), exactly one team is home
for w in weeks:
    for p in periods:
        for k, (i, j) in enumerate(pairs):
            m += home[w][p][k] <= y[w][p][k]            # cannot set home if game not scheduled here
            # If game is here, exactly one is home: home[i]=1 => i home, (1-home)=j home
            # Enforce "home only if played here" and sum over all (w,p) later
        # Also, across all pairs, if (w,p) has a game, its home var must be defined once:
        # but we already have exactly one game per (w,p), so no extra constraint needed

# ==================================== symmetry breaking ====================================
# Breaking1 : fix the first week
for p in periods:
    idx = pairs.index((2*p,2*p+1))  # Obtain the index of the pair (2p,2p+1)
    m += y[0][p][idx] == 1    # Fix the first week to be (0,1),(2,3),… (and fix home team) 
    m += home[0][p][idx] == 1 # Fix the first week to be (0,1),(2,3),… (and fix home team)

# Breaking2: fix which opponent team 0 faces in each week (period is free)
for w in range(W):     # w = 0..W-1
    opp = w + 1                   # team 0 plays team 1 in week 0, team 2 in week 1, ...
    k = pair_idx[(0, opp)]        # (0,opp) exists because pairs are i<j
    m += xsum(y[w][p][k] for p in periods) == 1

# Breaking3: team 0 plays in the diagonal slots (w=p, p) for p=0..P-1
for p in range(P):
    m += xsum(
        y[p][p][k]
        for k, (i, j) in enumerate(pairs)
        if i == 0   # because pairs are i<j, team 0 appears only as i
    ) == 1




# ====================================objective function ====================================
home_cnt = [m.add_var(var_type=INTEGER, lb=0) for _ in teams]

# Index precomputation (make the check faster in the loop)
I_of = {t: [k for k,(i,j) in enumerate(pairs) if i == t] for t in teams}
J_of = {t: [k for k,(i,j) in enumerate(pairs) if j == t] for t in teams}
# Count home matches for each team (sum over all (w,p) where they're designated home)
for t in teams:
    A = xsum(home[w][p][k] for w in weeks for p in periods for k in I_of[t])
    B = xsum(y[w][p][k] - home[w][p][k] for w in weeks for p in periods for k in J_of[t])
    m += home_cnt[t] == A + B

# Balance objective: minimize sum_t max(home_cnt[t], away_cnt[t]) with linearization
max_ha = [m.add_var(var_type=INTEGER, lb=0) for _ in teams]
balance = [m.add_var(var_type=INTEGER, lb=0) for _ in teams]
for t in teams:
    away = (W) - home_cnt[t]
    m += max_ha[t] >= home_cnt[t]
    m += max_ha[t] >= away
    m += balance[t] == (2*max_ha[t]-(n-1))

m.objective = xsum(balance)

# ==================================== OPTIMIZATION ====================================
if opt_enable:
    m.max_mip_gap = 0 # Get the optimal solution
    solution_name += " (OPT-version)"
else:   
    m.max_mip_gap = 0.5  # Stop once you’re within 50% of optimal (even if not proven). To get optimal, set to 0.0
start = time.perf_counter()
status = m.optimize(max_seconds=300)
end = time.perf_counter()
runtime= end - start

# ==================================== MAIN ====================================
# By the default the library try to find the optimal value if it fail returns the non-optimal results
optimal = False
if status == OptimizationStatus.OPTIMAL:
    optimal = True
    print(f"✅ Optimal solution found (opt = {m.objective_value})")
elif status == OptimizationStatus.FEASIBLE:
    print(f"✅ Feasible solution found but not proven optimal (opt = {m.objective_value})")
else:
    print("❌ No solution found (UNSAT OR TIME_EXCEEDED)")

data = import_json_solution(default_filename)

if m.num_solutions:
    # Build matrix: periods x weeks
    schedule = [[None for _ in weeks] for _ in periods]
    for w in weeks:
        for p in periods:
            for k, (i, j) in enumerate(pairs):
                if y[w][p][k].x >= 0.99:
                    if home[w][p][k].x >= 0.5:
                        schedule[p][w] = (i+1, j+1)   # i home, j away
                    else:
                        schedule[p][w] = (j+1, i+1)   # j home, i away

    export_time = runtime if optimal else 300
    data = add_solution_json(data , schedule , export_time , m.objective_value , optimal ,  solution_name=solution_name)
else:
    if status == OptimizationStatus.INFEASIBLE:
        data = add_solution_json(data, [], runtime, "None", True, solution_name=solution_name)
    else:
        data = add_solution_json(data, [], 300, "None", False, solution_name=solution_name)

export_json_solution(data , filename=default_filename)
    


# ========== DEBUG INFO ========== #
if debug_info:
    print("\n=== DEBUG INFO ===")
    print(f"Problem size: n={n}, W={W}, P={P}")
    print(f"Optimal bound: {m.objective_bound}")
    print(f"Couples generated: {pairs}")

    
