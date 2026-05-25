from itertools import combinations
from z3 import *
import numpy as np
from datetime import datetime
import json
import time
from common.utils import *



################################# PARAMETERS ###############################
script_path = ''                   # Name if this script is executed for debugging
docker_path = '/app/outputs/SAT/'  # Name if this script is executed from docker script
SEED_FOR_REPRODUTION = 0       # set to 0 for default; >0 for reproduce an attempt
team , weeks , periods , home , default_filename , optimized_version , precomputing_version = get_user_settings(sys.argv , docker_path , script_path)
timeout = 300000 # milliseconds
################################# PARAMETERS ###############################



################################# ENCODINGS - PAIRWISE ###############################
def at_least_one(bool_vars):
    return Or(bool_vars)

# Using naive-pairwise(O(n^2))
def at_most_one(bool_vars):
    return And([Not(And(pair[0], pair[1])) for pair in combinations(bool_vars, 2)])

# Using naive-pairwise(O(n^2))
def exactly_one(bool_vars):
    return And(at_least_one(bool_vars), at_most_one(bool_vars))

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




################################# DOMAIN DEFINITION ###############################
start1 = time.perf_counter()
# Define the variable
vars = np.empty((team , home , periods , weeks) , dtype=object)
for t in range(0,team):
    for h in range(0,home):    # home = 0 (team play away)   ;  home = 1 (team play at home)
        for p in range(0,periods):
            for w in range(0,weeks):
                if(h == 0):
                    #vars[t,h,p,w] = Bool(f"T{t+1}-P{p+1}-W{w+1}(AWAY)") # an other possible notation
                    vars[t,h,p,w] = Bool(f"X{t+1}{h}{p+1}{w+1}")  
                else:
                    #vars[t,h,p,w] = Bool(f"T{t+1}-P{p+1}-W{w+1}(HOME)") # an other possible notation
                    vars[t,h,p,w] = Bool(f"X{t+1}{h}{p+1}{w+1}") 

print("-------------------------------------------------------------------------------------------------")

model = Optimize()
################################# DOMAIN DEFINITION ###############################




################################# CONSTRAINT ###############################
# Constraint1 - Every team plays with every other team only once;
clauses = []
for t1 in range(0,team):
    for t2 in range(t1+1,team):
            for p in range(0,periods):
                for w in range(0,weeks):
                    t_i = Or(list(vars[t1,:,p,w].flatten()))
                    t_j = Or(list(vars[t2,:,p,w].flatten()))
                    clauses.append(And(t_i , t_j))
            model.add(at_most_one(clauses))
            # print("1 : number of clause in the at_least_one" , len(clauses)) # Dimension check
            clauses = []


# Constraint2 - Every team plays once at week
for t in range(0,team):
    for w in range(0,weeks):
        model.add(exactly_one( list(vars[t,:,:,w].flatten()) ))

# Constraint3 - Every team plays at most twice in the same period over the tournament.
for t in range(0,team):
    for p in range(0,periods):
        c = at_most_k( list(vars[t,:,p,:].flatten()) , k = 2 )
        model.add(c)

# Constraint 4 - Each game has exactly 2 team + Each game cannot be played by 2 home-team or 2 away-team
for h in range(home):
    for p in range(periods):
        for w in range(weeks):
            model.add(exactly_one([vars[t,h,p,w] for t in range(team)]  ))

# Constraint-Extra1 (in the first line, match are fixed)
model.add(And([ Or(vars[t,0,0,t], vars[t,1,0,t]) for t in range(team - 1) ]))
model.add(Or(vars[team-1,0,0,0] , vars[team-1,1,0,0]))

"""# Constraint-Extra1 (in the first,second column, match are fixed)
temp_list = []
half = team//2
for t in range(0, (team-1)):
    column =(t)//half
    line = t%half
    temp_list.append(Or(vars[t,0, line , column] , vars[t,1,line,column]))
pairwise.add(And(temp_list))"""

start2 = time.perf_counter()
init_time = start2-start1
print(f"Init finished! ({init_time:.2f}s)")
################################# CONSTRAINT ###############################



################################# MAIN ###############################
pairwise_model = SAT1(model , team , vars , default_filename , init_time , opt_enabled=optimized_version , timeout=timeout)

result_code = pairwise_model.solve()

if( result_code == 0 ) : # SAT
    print(f"SAT1-PAIRWISE : The model is satisfiable (SAT) ✅ - exits at least one solution! (🕒: {init_time:.2f} + {pairwise_model.solve_time:.2f} = {(init_time+pairwise_model.solve_time):.2f}s)")
    print("obj : " , pairwise_model.obj)
    pairwise_model.add_solution_json(solution_name=f'SAT1')
    pairwise_model.export_json_solution()
    pairwise_model.visualize_solution_raw("raw_solution.txt")
elif( result_code == 1 ) : # UNSAT
    print("The model is unsatisfiable (UNSAT) ❌  - doesn't exits solution at all")
    pairwise_model.add_empty_solution_json(solution_name=f'SAT1')
    pairwise_model.export_json_solution()
else: # UNKNOWN
    print("The solver returned UNKNOWN (timeout reached) ⚠️")
    pairwise_model.add_empty_solution_json(solution_name=f'SAT1', timed_out=True)
    pairwise_model.export_json_solution()
print("-------------------------------------------------------------------------------------------------")
################################# MAIN ###############################









            
