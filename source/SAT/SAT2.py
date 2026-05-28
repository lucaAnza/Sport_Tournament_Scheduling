#!/usr/bin/env python3
from itertools import combinations
from z3 import *
import numpy as np
from datetime import datetime
import json, sys, time
from common.utils import *


################################# PARAMETERS ###############################
debug_info = False
script_path = ''                   # Name if this script is executed for debugging
docker_path = '/app/outputs/SAT/'  # Name if this script is executed from docker script
SEED_FOR_REPRODUTION = 0       # set to 0 for default; >0 for reproduce an attempt
team , weeks , periods , home , default_filename , optimized_version , precomputing_version = get_user_settings(sys.argv , docker_path , script_path)
timeout = 300000 # milliseconds
SOLUTION_NAME = 'SAT2'
################################# PARAMETERS ###############################

# Z3 params
set_param('sat.cardinality.solver', True)   # Specialized encodings for cardinality constraints
if SEED_FOR_REPRODUTION:
    set_param('random_seed', SEED_FOR_REPRODUTION)

# ========================== ROUND-ROBIN PAIRS GENERATION ============================
def round_robin_pairs(n):
    arr = list(range(n))
    weeks_list = []
    for w in range(n - 1):
        pairs = []
        for i in range(n // 2):
            a = arr[i]
            b = arr[n - 1 - i]
            if a < b: pairs.append((a, b))
            else:     pairs.append((b, a))
        weeks_list.append(pairs)
        # rotate (fix arr[0])
        arr = [arr[0]] + [arr[-1]] + arr[1:-1]
    return weeks_list


################################# ENCODINGS - PAIRWISE ###############################
def at_least_one(bool_vars):
    return Or(bool_vars)

# Using naive-pairwise (O(n^k+1))
def at_most_k(bool_vars, k):
    return And([Or([Not(x) for x in X]) for X in combinations(bool_vars, k + 1)])
 
# Using naive-pairwise (O(n^k+1))
def at_least_k(bool_vars, k):
    return at_most_k([Not(var) for var in bool_vars], len(bool_vars)-k)

# Using naive-pairwise (O(n^k+1))
def exactly_k(bool_vars, k):
    return And(at_most_k(bool_vars, k), at_least_k(bool_vars, k))
################################# ENCODINGS - PAIRWISE ###############################

################################# ENCODINGS - HEULE ###############################
# naive pairwise-encoding
def at_most_one(bool_vars):
    return And([Not(And(pair[0], pair[1])) for pair in combinations(bool_vars, 2)])

def at_most_one_heule(bool_vars, name ):
    if len(bool_vars) <= 4:
        return And(at_most_one(bool_vars))
    y = Bool(f"y_{name}")
    # Before it was : return And(And(at_most_one_np(bool_vars[:3] + [y])), And(at_most_one(bool_vars[3:] + [Not(y)], name+"_")))
    group1 = bool_vars[:3] + [y]
    group2 = [Not(y)] + bool_vars[3:]  # Prepend ¬y for clarity
    return And(
        at_most_one_heule(group1, name + "_left"),   # TODO : check if left and right are the best
        at_most_one_heule(group2, name + "_right")   # TODO : check if left and right are the best
    )   

def exactly_one_heule(bool_vars, name = 'A'):
    return And(at_most_one_heule(bool_vars, name), at_least_one(bool_vars))
################################# ENCODINGS - HEULE ###############################


# ============================== MODEL VARS =================================
print("-------------------------------------------------------------------------------------------------")
start1 = time.perf_counter()
init_progress = ProgressPrinter("model init running", timeout // 1000, start1)
init_progress.start()
timeout_solution_name = solution_name_with_settings(SOLUTION_NAME, optimized_version, precomputing_version)
M = [[[Bool(f"M_{t1}_{t2}_w{w}") for w in range(weeks)] for t2 in range(team)] for t1 in range(team)] # t1,t2 plays in week w
P = [[[Bool(f"P_t{t}_p{p}_w{w}") for w in range(weeks)] for p in range(periods)] for t in range(team)] # team t is assigned to period p in week w
HOME = [[Bool(f"HOME_{t}_w{w}") for w in range(weeks)] for t in range(team)] # team t is home in week w
AWAY = [[Bool(f"AWAY_{t}_w{w}") for w in range(weeks)] for t in range(team)] # team t is away in week w  
model = Solver()
# ============================== CONSTRAINTS ================================

# Constraint 1 : every team plays with every other team only once;
for t1 in range(team):
    exit_if_init_timeout(start1, timeout, default_filename, timeout_solution_name, init_progress)
    for t2 in range(t1 + 1, team):
        model.add(PbEq([(M[t1][t2][w], 1) for w in range(weeks)], 1))

# Constraint2 : each team play exactly one per week: sum over p of P[t][p][w] == 1
for w in range(weeks):
    exit_if_init_timeout(start1, timeout, default_filename, timeout_solution_name, init_progress)
    for t in range(team):
        # S.add(PbEq([(P[t][p][w], 1) for p in range(periods)], 1))   # SAT translation of x1​+x2​+x3​ = 1 (PbEq also enabled weight 3x1 + 4x2 + ...)
        model.add(exactly_k([P[t][p][w] for p in range(periods)], 1))   # TODO : use exactly one of sequential,heule,bitwise

# Constraint3 : each team plays two per period : sum over weeks of P[t][p][w] <= 2
for t in range(team):
    exit_if_init_timeout(start1, timeout, default_filename, timeout_solution_name, init_progress)
    for p in range(periods):
        model.add(PbLe([(P[t][p][w], 1) for w in range(weeks)], 2))

# Constraint4 : Home/away consistency: when (t1,t2) plays in w, HOME differs
for w in range(weeks):
    exit_if_init_timeout(start1, timeout, default_filename, timeout_solution_name, init_progress)
    for t1 in range(team):
        for t2 in range(t1 + 1, team):
            model.add(Implies(M[t1][t2][w], Xor(HOME[t1][w], HOME[t2][w])))
            
# Constraint5 : Each game is played by 2 team : sum over t of P[t][p][w] == 2
for w in range(weeks):
    exit_if_init_timeout(start1, timeout, default_filename, timeout_solution_name, init_progress)
    for p in range(periods):
        model.add(PbEq([(P[t][p][w], 1) for t in range(team)], 2))     # SAT translation of x1​+x2​+x3​ =2 (PbEq also enabled weight 3x1 + 4x2 + ...)
        # S.add(exactly_k([P[t][p][w] for t in range(team)], 2))     # TODO : use exactly k of sequential 

#Link periods variable (P) to pair variable (M)
for w in range(weeks):
    exit_if_init_timeout(start1, timeout, default_filename, timeout_solution_name, init_progress)
    for t1 in range(team):
        for t2 in range(t1 + 1, team):
            # If the pair plays in week w, they share exactly one period
            model.add(Implies(M[t1][t2][w], Or([And(P[t1][p][w], P[t2][p][w]) for p in range(periods)])))
            
            # If two teams share (period p, week w), then that (t1,t2) is the match that week
            for p in range(periods):
                model.add(Implies(And(P[t1][p][w], P[t2][p][w]), M[t1][t2][w]))

# ================================ PRECOMPUTING ==================================
if precomputing_version:
    pre1 = time.perf_counter()
    # Generate possible pairs
    rr_weeks = round_robin_pairs(team)  # weeks -> list[(a,b)]
    
    # Define only the possible couple of match
    M_true = set()  # start with an empty set
    # We are defining only the matches that can happen according to round-robin in a specific week
    for w, pairs in enumerate(rr_weeks):      
        for a, b in pairs:                     
            t1 = min(a, b)                     
            t2 = max(a, b)
            M_true.add((t1, t2, w))  # Model not involved           

    # Say that is sat only if the generated couple are the one in M_true
    for t1 in range(team):
        exit_if_init_timeout(start1, timeout, default_filename, timeout_solution_name, init_progress)
        for t2 in range(t1+1, team):
            for w in range(weeks):
                if (t1, t2, w) in M_true:
                    model.add(M[t1][t2][w])
                else:
                    model.add(Not(M[t1][t2][w]))
    pre2 = time.perf_counter()
    precomputing_time = pre2-pre1
    print(f"\nPrecomputing time :  ({precomputing_time:.2f}s)")

exit_if_init_timeout(start1, timeout, default_filename, timeout_solution_name, init_progress)
start2 = time.perf_counter()
init_progress.stop()
init_time = start2 - start1
print(f"Init finished! ({init_time:.2f}s)")



################################# MAIN ###############################
sequential_model = SAT2(model , team , M , HOME , P , default_filename , init_time , opt_enabled=optimized_version , precomputing_enabled = precomputing_version , timeout = timeout)

result_code = sequential_model.solve()
if( result_code == 0) : # SAT  
    print(f"SAT2 : The model is satisfiable (SAT) ✅ - exits at least one solution! (🕒: {init_time:.2f} + {sequential_model.solve_time:.2f} = {(init_time+sequential_model.solve_time):.2f}s)")
    print("obj : " , sequential_model.obj)
    sequential_model.add_solution_json(solution_name=f'{SOLUTION_NAME}')
    sequential_model.export_json_solution()
    """for d in sequential_model.model.decls():
        print(f"{d.name()} = {sequential_model.model[d]}")"""
elif(result_code == 1): # UNSAT
    print("The model is unsatisfiable (UNSAT) ❌  - doesn't exits solution at all")
    sequential_model.add_empty_solution_json(solution_name=f'{SOLUTION_NAME}')
    sequential_model.export_json_solution()
else: # UNKNOWN
    print("The solver returned UNKNOWN (timeout reached) ⚠️")
    sequential_model.add_empty_solution_json(solution_name=f'{SOLUTION_NAME}', timed_out=True)
    sequential_model.export_json_solution()
print("-------------------------------------------------------------------------------------------------")
################################# MAIN ###############################



############################## DEBUG INFO ###############################
if debug_info:
    print("\n=== DEBUG INFO ===")
    print(f"Problem size: n={team}, W={weeks}, P={periods}")
    print("\nRound-robin generation example : " , f"n = {team}")
    temp_round_robin = round_robin_pairs(team)
    # Fix index
    for i in range(len(temp_round_robin)):
        temp_round_robin[i] = [(a+1 , b+1) for (a,b) in temp_round_robin[i]]
    for w in range(weeks):
        print("IN THE WEEK ", w ," will be played only this matches", " = " , temp_round_robin[w])
        
