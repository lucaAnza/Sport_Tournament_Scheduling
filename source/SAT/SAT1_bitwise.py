from itertools import combinations
from z3 import *
import numpy as np
from datetime import datetime
import time
import sys
from common.utils import *


################################# PARAMETERS ###############################
script_path = ''                   # Name if this script is executed for debugging
docker_path = '/app/outputs/SAT/'  # Name if this script is executed from docker script
SEED_FOR_REPRODUTION = 0       # set to 0 for default; >0 for reproduce an attempt
team , weeks , periods , home , default_filename , optimized_version , precomputing_version = get_user_settings(sys.argv , docker_path , script_path)
timeout = 10000 # milliseconds
################################# PARAMETERS ###############################



################################# ENCODINGS - BITWISE ###############################
def toBinary(num, length = None):
    num_bin = bin(num).split("b")[-1]
    if length:
        return "0"*(length - len(num_bin)) + num_bin
    return num_bin
    
def at_most_one_bitwise(bool_vars, name = 'A'):
    constraints = []
    n = len(bool_vars)
    m = math.ceil(math.log2(n))
    r = [Bool(f"r_{name}_{i}") for i in range(m)]
    binaries = [toBinary(i, m) for i in range(n)]
    for i in range(n):
        for j in range(m):
            phi = Not(r[j])
            if binaries[i][j] == "1":
                phi = r[j]
            constraints.append(Or(Not(bool_vars[i]), phi))        
    return And(constraints)

def exactly_one_bitwise(bool_vars, name = 'A'):
    return And(at_least_one(bool_vars), at_most_one_bitwise(bool_vars, name))
################################# ENCODINGS - BITWISE ###############################

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






################################# DOMAIN DEFINITION ###############################
print("-------------------------------------------------------------------------------------------------")
start1 = time.perf_counter()
init_progress = ProgressPrinter("model init running", timeout // 1000, start1)   # Define thread for timeout during model initialization (in seconds)
init_progress.start()
timeout_solution_name = solution_name_with_settings('SAT1-bitwise', optimized_version)
# Define the variable
vars = np.empty((team , home , periods , weeks) , dtype=object)
for t in range(0,team):
    exit_if_init_timeout(start1, timeout, default_filename, timeout_solution_name, init_progress)
    for h in range(0,home):    # home = 0 (team play away)   ;  home = 1 (team play at home)
        for p in range(0,periods):
            for w in range(0,weeks):
                if(h == 0):
                    #vars[t,h,p,w] = Bool(f"T{t+1}-P{p+1}-W{w+1}(AWAY)") # an other possible notation
                    vars[t,h,p,w] = Bool(f"X{t+1}{h}{p+1}{w+1}")  
                else:
                    #vars[t,h,p,w] = Bool(f"T{t+1}-P{p+1}-W{w+1}(HOME)") # an other possible notation
                    vars[t,h,p,w] = Bool(f"X{t+1}{h}{p+1}{w+1}") 


model = Optimize()  # Use Solver() if you don't use optimization function

################################# DOMAIN DEFINITION ###############################




################################# CONSTRAINT ###############################
# Constraint1 - Every team plays with every other team only once;
clauses = []
for t1 in range(0,team):
    exit_if_init_timeout(start1, timeout, default_filename, timeout_solution_name, init_progress)
    for t2 in range(t1+1,team):
            for p in range(0,periods):
                for w in range(0,weeks):
                    t_i = Or(list(vars[t1,:,p,w].flatten()))
                    t_j = Or(list(vars[t2,:,p,w].flatten()))
                    clauses.append(And(t_i , t_j))
            model.add(at_most_one_bitwise(clauses , name = f't{t1}t{t2}'))
            # print("1 : number of clause in the at_least_one" , len(clauses)) # Dimension check
            clauses = []


# Constraint2 - Every team plays once at week
for t in range(0,team):
    exit_if_init_timeout(start1, timeout, default_filename, timeout_solution_name, init_progress)
    for w in range(0,weeks):
        model.add(exactly_one_bitwise( list(vars[t,:,:,w].flatten()) , name = f't{t}w{w}'))

# Constraint3 - Every team plays at most twice in the same period over the tournament.
for t in range(0,team):
    exit_if_init_timeout(start1, timeout, default_filename, timeout_solution_name, init_progress)
    for p in range(0,periods):
        c = at_most_k( list(vars[t,:,p,:].flatten()) , k = 2 )
        model.add(c)

# Constraint 4 - Each game has exactly 2 team + Each game cannot be played by 2 home-team or 2 away-team
for h in range(home):
    exit_if_init_timeout(start1, timeout, default_filename, timeout_solution_name, init_progress)
    for p in range(periods):
        for w in range(weeks):
            model.add(exactly_one_bitwise([vars[t,h,p,w] for t in range(team)] , name = f'h{h}p{p}w{w}') )


"""
### V1 
# Constraint4 - Each game has exactly 2 team
clauses = []
for p in range(0,periods):
    for w in range(0,weeks):
        for t in range(team):
            x = Or(list(vars[t,:,p,w].flatten()))
            clauses.append(x)
        bitwise.add(exactly_k(clauses,  k = 2))
        # print("4.2 number of clause in the exactly_k: " , len(clauses)) # Dimension check
        clauses = []
        
# Constraint5 - Each game cannot be played by 2 home-team or 2 away-team 
for h in range(home):
    for p in range(0,periods):
        for w in range(0,weeks):
            bitwise.add(at_most_one_bitwise(list(vars[:,h,p,w].flatten()) , name = f"h{h}p{p}w{w}" ))
            # print("4.3 number of clause in the at_most_one : " , len(list(vars[:,h,p,w].flatten())))  # Dimension check

# Constraint6 - Each team in a day play at home or away cannot both
for t in range(team):
    for p in range(periods):
        for w in range(weeks):
            bitwise.add(at_most_one_bitwise(list(vars[t,:,p,w].flatten()) , name = f"t{t}p{p}w{w}" ))  
            # print("4.1 number of clause in the at_most_one: " , len(list(vars[t,:,p,w].flatten()))) # Dimension check 
"""
exit_if_init_timeout(start1, timeout, default_filename, timeout_solution_name, init_progress)
start2 = time.perf_counter()
init_progress.stop()
init_time = start2-start1
print(f"Init finished! ({init_time:.2f}s)")
################################# CONSTRAINT ###############################




################################# MAIN ###############################
bitwise_model = SAT1(model , team , vars , default_filename , init_time , opt_enabled=optimized_version , timeout = timeout)

result_code = bitwise_model.solve()

if( result_code == 0 ) : # SAT
    print(f"SAT1-BITWISE : The model is satisfiable (SAT) ✅ - exits at least one solution! (🕒: {init_time:.2f} + {bitwise_model.solve_time:.2f} = {(init_time+bitwise_model.solve_time):.2f}s)")
    print(bitwise_model.obj)
    bitwise_model.add_solution_json(solution_name=f'SAT1-bitwise')
    bitwise_model.export_json_solution()
elif( result_code == 1 ) : # UNSAT
    print("The model is unsatisfiable (UNSAT) ❌  - doesn't exits solution at all")
    bitwise_model.add_empty_solution_json(solution_name=f'SAT1-bitwise')
    bitwise_model.export_json_solution()
else: # UNKNOWN
    print("The solver returned UNKNOWN (timeout reached) ⚠️")
    bitwise_model.add_empty_solution_json(solution_name=f'SAT1-bitwise', timed_out=True)
    bitwise_model.export_json_solution()
print("-------------------------------------------------------------------------------------------------")


################################# MAIN ###############################









            
