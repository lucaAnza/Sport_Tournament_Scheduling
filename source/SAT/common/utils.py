from datetime import datetime
import sys
import json
from z3 import *
import time
import threading
import os
from abc import abstractmethod
import argparse
from itertools import combinations


################################# WRAP CLASS #########################################
class ProgressPrinter:
    def __init__(self, label, total_seconds=None, start_time=None , offset = None):
        self.label = label
        self.total_seconds = total_seconds
        self.start_time = start_time
        self.stop_event = threading.Event()
        self.thread = None
        self.last_message_len = 0
        self.offset = offset

    def start(self):
        self.stop_event.clear()
        if self.start_time is None:
            self.start_time = time.perf_counter()
        self.thread = threading.Thread(target=self._print_progress, daemon=True)
        self.thread.start()

    def stop(self):
        if self.thread is None:
            return
        self.stop_event.set()
        self.thread.join()
        self.thread = None
        sys.stdout.write("\r" + " " * self.last_message_len + "\r")
        sys.stdout.flush()

    # the function that runs in the thread
    def _print_progress(self): 
        while not self.stop_event.is_set():
            if self.offset is not None:
                elapsed = int(time.perf_counter() - self.start_time + self.offset)
            else:
                elapsed = int(time.perf_counter() - self.start_time)
            if self.total_seconds is None:
                message = f"{self.label} {elapsed}s"
            else:
                message = f"{self.label} {min(elapsed, self.total_seconds)}s/{self.total_seconds}s"
            self.last_message_len = max(self.last_message_len, len(message))
            sys.stdout.write("\r" + message)
            sys.stdout.flush()
            self.stop_event.wait(1)



################################# SAT initialization HELPERS #########################################
def solution_name_with_settings(solution_name, opt_enabled=False, precomputing_enabled=False):
    if opt_enabled:
        solution_name = solution_name + '(OPT-version)'
    if precomputing_enabled:
        solution_name = solution_name + '(PRECOMPUTING)'
    return solution_name


def import_json_solution_file(filename):
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"File {filename} not found. Returning empty dictionary.")
        return {}
    except Exception:
        print(f"Error during file reading. Returning empty dictionary.")
        return {}


def export_json_solution_file(data, filename):
    dirpath = os.path.dirname(filename)
    if dirpath:
        os.makedirs(dirpath, exist_ok=True)
    with open(filename, "w") as f:
        json.dump(data, f, indent=4)
        f.write("\n")
    print(f"Successfully exported the json solution  ('{filename}')")


def exit_if_init_timeout(start_time, timeout_ms, solution_filename, solution_name, progress_printer=None):
    elapsed_ms = int((time.perf_counter() - start_time) * 1000)
    if elapsed_ms < timeout_ms:
        return

    if progress_printer is not None:
        progress_printer.stop()

    data = import_json_solution_file(solution_filename)
    data[solution_name] = {
        'time': timeout_ms // 1000,
        'optimal': False,
        'obj': "None",
        'sol': []
    }
    print(f"Model initialization reached timeout ({timeout_ms // 1000}s)")
    export_json_solution_file(data, solution_filename)
    raise SystemExit(0)


class ContextSolver():
    
    def __init__(self , z3_solver , team , solution_filename , init_time , opt_enabled , timeout):

        if not(team % 2 == 0):
            raise ValueError("Team must be a non-negative integer")

        self.opt_enabled = opt_enabled
        self.proved_optimal = not opt_enabled
        self.obj = None
        self.init_time = init_time
        self.solve_time = -1
        self.solver = z3_solver  # Solver
        self.model = None        # ModelRef  (A solution instance)
        self.team = team
        self.week = self.team - 1
        self.periods = self.team // 2
        self.home = 2
        self.solution_filename = solution_filename
        self.data = self.import_json_solution()
        self.timeout = timeout
        self.solve_start = None
        self.progress_printer = None
        print("solver timeout is set to : " , self.timeout , "milliseconds" , f"({self.timeout//1000} seconds)")
        self.solver.set(timeout=self.remaining_timeout_ms())

    def remaining_timeout_ms(self):
        elapsed_ms = int(self.init_time * 1000)
        if self.solve_start is not None:
            elapsed_ms = elapsed_ms + int((time.perf_counter() - self.solve_start) * 1000) # init_time + solve_time

        return max(0, self.timeout - elapsed_ms)

    def check_with_remaining_timeout(self):
        remaining = self.remaining_timeout_ms()
        if remaining <= 0:
            return z3.unknown
        self.solver.set(timeout=remaining)
        return self.solver.check()

    # Used in the optimization phase, cause we add a lot of constraints (Timeout fixed)
    def add_at_most_k_with_remaining_timeout(self, bool_vars, k, chunk_size=500):
        if k >= len(bool_vars):
            return True
        pending = []
        for combo in combinations(bool_vars, k + 1):
            if self.remaining_timeout_ms() <= 0:
                return False
            pending.append(Or([Not(x) for x in combo]))
            if len(pending) >= chunk_size:
                self.solver.add(pending)
                pending = []
        if pending:
            self.solver.add(pending)
        return True
    
    # Used in the optimization phase, cause we add a lot of constraints (Timeout fixed)
    def add_at_least_k_with_remaining_timeout(self, bool_vars, k, chunk_size=500):
        if k <= 0:
            return True
        if k > len(bool_vars):
            return False
        max_false = len(bool_vars) - k
        pending = []
        for combo in combinations(bool_vars, max_false + 1):
            if self.remaining_timeout_ms() <= 0:
                return False
            pending.append(Or(list(combo)))
            if len(pending) >= chunk_size:
                self.solver.add(pending)
                pending = []
        if pending:
            self.solver.add(pending)
        return True

    def start_progress_printer(self):
        timeout_seconds = self.timeout // 1000
        self.progress_printer = ProgressPrinter("process running", timeout_seconds, self.solve_start , offset=self.init_time)
        self.progress_printer.start()

    def stop_progress_printer(self):
        if self.progress_printer is None:
            return
        self.progress_printer.stop()
        self.progress_printer = None

    def import_json_solution(self):
        try:
            with open(self.solution_filename, "r") as f:
                data = json.load(f)
            return data
        except FileNotFoundError:
            return {} 
        except Exception:
            print(f"Error during file reading. Returning empty dictionary.") 
            return {} 
        
    def export_json_solution(self , indent=4, compact_keys=("sol",)):
    
        def write(obj, f, level=0, parent_key=None):
            pad = " " * (level * indent)

            if isinstance(obj, dict):
                f.write("{\n")
                items = list(obj.items())
                for i, (k, v) in enumerate(items):
                    f.write(pad + " " * indent + json.dumps(k) + ": ")
                    write(v, f, level + 1, parent_key=k)
                    if i < len(items) - 1:
                        f.write(",\n")
                f.write("\n" + pad + "}")

            elif isinstance(obj, list):
                # special formatting for sol
                if parent_key in compact_keys:
                    f.write("[\n")
                    for i, item in enumerate(obj):
                        f.write(pad + " " * indent)
                        # compact dump of each inner list
                        f.write(json.dumps(item, separators=(",", ":")))
                        if i < len(obj) - 1:
                            f.write(",\n")
                    f.write("\n" + pad + "]")
                else:
                    f.write("[\n")
                    for i, item in enumerate(obj):
                        f.write(pad + " " * indent)
                        write(item, f, level + 1, parent_key=None)
                        if i < len(obj) - 1:
                            f.write(",\n")
                    f.write("\n" + pad + "]")

            else:
                f.write(json.dumps(obj))

        try:
            with open(self.solution_filename, "w") as f:
                write(self.data, f, 0)
                f.write("\n")
        except Exception as e:
            print(f"Error writing JSON file: {e}")

    @abstractmethod
    def add_solution_json(self, solution_name):
        # TO IMPLEMENT IN SUBCLASS
        pass

    def empty_result_entry(self, timed_out=False):
        return {
            'time': self.timeout // 1000 if timed_out else int(self.solve_time),
            'optimal': not timed_out,
            'obj': "None",
            'sol': []
        }

    def solve(self):
        start = time.perf_counter() # -----------------------------------------------------------------------------TIME(START)
        self.solve_start = start 
        self.start_progress_printer()
        try:
            find_one_at_least_one_solution = False
            sat_result = self.check_with_remaining_timeout()   # Start the SAT search and fill the variable model with the solution (ModelRef)
            if(sat_result == z3.sat): 
                find_one_at_least_one_solution = True
                self.model = self.solver.model()
                self.obj = self.compute_obj_function()
                # Optimality research (in this phase you have already found one solution)
                if(self.opt_enabled):
                    self.solve_opt()
            elif(sat_result == z3.unknown):
                self.solve_time = min(time.perf_counter() - start, max(0, self.timeout / 1000 - self.init_time))
                return 2 # UNKNOWN (timeout or other solver failure)

            end = time.perf_counter()  # ------------------------------------------------------------------------------- TIME(END)
            self.solve_time = min(end - start, max(0, self.timeout / 1000 - self.init_time))
        finally:
            self.stop_progress_printer()
        if(find_one_at_least_one_solution):
            return 0
        else:
            return 1
    
    @abstractmethod
    def compute_obj_function(self):
        # TO IMPLEMENT IN SUBCLASS
        pass

    @abstractmethod
    def solve_opt(self):
        # TO IMPLEMENT IN SUBCLASS
        pass
    

class SAT1(ContextSolver):

    def __init__(self , z3_solver , team , vars , solution_filename , init_time , opt_enabled , timeout) :
        self.vars = vars
        super().__init__(z3_solver , team , solution_filename , init_time , opt_enabled , timeout)

    def compute_obj_function(self):
        vars = self.vars
        team_imbalance = [Abs(Sum([ If(vars[t,0,p,w], 1, 0) - If(vars[t,1,p,w], 1, 0) for p in range(self.periods) for w in range(self.week) ])) for t in range(self.team)]
        total_imbalance = Sum(team_imbalance)
        obj = self.model.evaluate(total_imbalance)
        return obj.as_long()

    def solution_name(self, solution_name):
        if(self.opt_enabled) : solution_name = solution_name + '(OPT-version)'
        return solution_name
    
    def add_solution_json(self , solution_name ):
        
        solution_name = self.solution_name(solution_name)
        vars = self.vars
        
        match = ['X','X']
        
        sol_list = []
        for p in range(self.periods):
            period_list = [] # Create one new period list
            for w in range(self.week):
                for t in range(self.team):
                    if(z3.is_true(self.model[vars[t, 0, p, w]])):
                        match[1] = t+1
                    if(z3.is_true(self.model[vars[t, 1, p, w]])):
                        match[0] = t+1
                period_list.append(match)  # Insert one match
                match = ['X','X']
            sol_list.append(period_list)
        
        optimal = (not self.opt_enabled) or self.proved_optimal
        time = int(self.solve_time)
        if not optimal: 
            time = self.timeout // 1000

        new_entry = {}
        new_entry['time'] = time
        new_entry['optimal'] = optimal
        new_entry['obj'] = int(self.obj) if self.opt_enabled else "None"
        new_entry['sol'] = sol_list
        self.data[solution_name] = new_entry

    def add_empty_solution_json(self, solution_name, timed_out=False):
        self.data[self.solution_name(solution_name)] = self.empty_result_entry(timed_out)

    def solve_opt(self):
        sat_result = sat
        self.solver.push()  # Create a snapshot of the model
        upper_bound = (self.periods*self.week)//2
        # Linear research (every team the upperbound is decreased of 1)
        while sat_result == sat and self.remaining_timeout_ms() > 0:
            self.model = self.solver.model()
            # Constraint for optimality
            for t in range(self.team):  
                for h in range(self.home):
                    if self.remaining_timeout_ms() <= 0:
                        sat_result = unknown
                        break
                    added = self.add_at_most_k_with_remaining_timeout(list(self.vars[t,h,:,:].flatten()), upper_bound)
                    if not added:
                        sat_result = unknown
                        break
                if sat_result == unknown:
                    break
            if sat_result == sat:
                sat_result = self.check_with_remaining_timeout() 
            upper_bound = upper_bound - 1
        
        self.proved_optimal = (sat_result == unsat)
        self.solver.pop() # Restored the status of the solver (removed all constraint about optimality)
        self.obj = self.compute_obj_function()

    def visualize_solution_raw(self , file_name):
        
        m = self.model

        # Choose output destination
        if file_name:
            f = open(file_name, "w")
            output = f
        else:
            output = sys.stdout

        try:
            print(datetime.now() , file=output)
            for t in range(self.team):
                print(f"\n\n----------TEAM {t+1}----------", file=output)
                for h in range(self.home):  # home = 0 (away), 1 (home)
                    label = "away : " if h == 0 else "home : "
                    print(label, file=output)

                    for p in range(self.periods):
                        for w in range(self.week):
                            temp = z3.is_true(m[self.vars[t, h, p, w]])
                            print(int(temp), end=" ", file=output)
                        print(file=output)  # Newline after each week row
                    
                print(f"-----------------------------", file=output)
        finally:
            if file_name:
                f.close()


class SAT2(ContextSolver):

    def __init__(self , z3_solver , team , M , HOME , P, solution_filename , init_time , opt_enabled , precomputing_enabled , timeout) :
        self.precomputing_enable = precomputing_enabled
        self.M = M
        self.HOME = HOME
        self.P = P
        super().__init__(z3_solver , team , solution_filename , init_time , opt_enabled , timeout)

    def pack_week_pairs_from_model(self , model : ModelRef):
        """For each week, return a list of (home_team, away_team) ordered by period p=0..periods-1."""
        weeks_pairs = [[] for _ in range(self.week)]
        for w in range(self.week):
            for p in range(self.periods):
                teams_here = [t for t in range(self.team) if is_true(model[self.P[t][p][w]])]
                assert len(teams_here) == 2, f"Week {w}, period {p} does not have exactly 2 teams."
                t1, t2 = teams_here[0], teams_here[1]
                t1_play_at_home = is_true(model[self.HOME[t1][w]])
                if(t1_play_at_home):
                    home_team , away_team = t1 , t2
                else:
                    home_team , away_team = t2 , t1
                weeks_pairs[w].append((home_team, away_team))
        return weeks_pairs

    def compute_obj_function(self):   
        team_imbalance = []
        matches = self.team - 1 # Each team plays always n-1 match
        
        # Compute team_imbalance for each team 
        for t in range(self.team):
            homes = Sum([If(self.HOME[t][w], 1, 0) for w in range(self.week)]) 
            imbalance_of_one_team =  Abs( (matches - homes) - homes)  # ABS (|Away| - |Home|)
            team_imbalance.append(imbalance_of_one_team)  
            # print(f"team{t} : {self.model.evaluate(imbalance_of_one_team)}")
        
        # Total sum for each team_imbalance
        total_imbalance = Sum(team_imbalance)
        obj = self.model.evaluate(total_imbalance)
        return obj.as_long()

    def solution_name(self, solution_name):
        if(self.opt_enabled) : solution_name = solution_name + '(OPT-version)'
        if(self.precomputing_enable) : solution_name = solution_name + '(PRECOMPUTING)'
        return solution_name

    def add_solution_json(self , solution_name):
        solution_name = self.solution_name(solution_name)

        # Build a periods×weeks array of matches [home,away] using the model
        sol_list = [[['X', 'X'] for _ in range(self.week)] for __ in range(self.periods)]
        packed = self.pack_week_pairs_from_model(self.model)  # per week: list of (home, away) following period order
        for w in range(self.week):
            for p, (h, a) in enumerate(packed[w]):
                sol_list[p][w] = [h + 1, a + 1]  # 1-based
        optimal = (not self.opt_enabled) or self.proved_optimal
        time = int(self.solve_time)
        if not optimal:
            time = self.timeout // 1000
        new_entry = {
            'time': time,
            'optimal': optimal,
            'obj': int(self.obj) if self.opt_enabled else "None",
            'sol': sol_list
        }
        self.data[solution_name] = new_entry
        return self.data

    def add_empty_solution_json(self, solution_name, timed_out=False):
        self.data[self.solution_name(solution_name)] = self.empty_result_entry(timed_out)
        return self.data
    
    def solve_opt(self):
        sat_result = sat
        self.solver.push()  # Create a snapshot of the model
        lower_bound = 1

        # Linear research (every team the upperbound is decreased of 1)
        while sat_result == sat and self.remaining_timeout_ms() > 0:
            # Constraint for optimality
            for t in range(self.team):                           
                if self.remaining_timeout_ms() <= 0:
                    sat_result = unknown
                    break
                home_added = self.add_at_least_k_with_remaining_timeout([self.HOME[t][w] for w in range(self.week)], lower_bound)
                away_added = self.add_at_least_k_with_remaining_timeout([Not(self.HOME[t][w]) for w in range(self.week)], lower_bound)
                if not home_added or not away_added:
                    sat_result = unknown
                    break
            if sat_result == sat:
                sat_result = self.check_with_remaining_timeout() 
            if(sat_result == sat):
                self.model = self.solver.model()
            lower_bound = lower_bound + 1
        
        self.proved_optimal = (sat_result == unsat)
        self.solver.pop()     # Restored the status of the solver (removed all constraint about optimality)
        self.obj = self.compute_obj_function()
################################# WRAP CLASS #########################################




################################# I/O FUNCTIONS #########################################
def _yes(prompt: str) -> bool:
    return input(prompt).strip().lower() in ("y", "yes", "true", "1")

def get_user_settings(argv, docker_path, script_path):

    parser = argparse.ArgumentParser(
        prog="scheduler",
        description="Sports Tournament Scheduler settings"
    )
    
    # team is optional on the CLI; if omitted we fall back to interactive prompts
    parser.add_argument("team", type=int, nargs="?", help="Number of teams")
    parser.add_argument("--optimized", action="store_true", help="Look for the optimal solution")
    parser.add_argument("--docker", action="store_true", help="Needed for using the right path")
    parser.add_argument("--precomputing", action="store_true", help="Enable precomputing version")

    # Parse given argv (expects full sys.argv-like list)
    args = parser.parse_args(argv[1:])

    # See if is launched by docker
    docker_mode = args.docker
    
    # Interactive fallback if team was not provided
    if args.team is None:
        team = int(input("\nHow many teams do you want ? "))
        # SAT1 scripts doesn't have optimized version
        if("SAT1" in argv[0]):
            precomputing_version = False
        else:
            precomputing_version = _yes("Do you want precomputing version ? (y/n) ")
        optimized_version = _yes("Do you want optimized version ? (y/n)")
        
    else:
        team = args.team
        optimized_version = args.optimized
        precomputing_version = args.precomputing

    # Derivated variables
    default_filename = docker_path + str(team) + ".json" if docker_mode else script_path + str(team) + ".json"
    weeks = team - 1
    periods = team // 2
    home = 2

    return team, weeks, periods, home, default_filename, optimized_version, precomputing_version


# m : is the output of s.model()
def visualize_solution_humanreadable(m, team , file_name=None):
    
    # Define problem size
    weeks   = team - 1
    periods = team // 2
    home  = 2 

    # Choose output destination
    if file_name:
        f = open(file_name, "w")
        output = f
    else:
        output = sys.stdout

    try:
        print(datetime.now() , file=output)
        print(f"Solution for n = {team}" , file=output)
        print(f"Format is HOME - AWAY  (ex : 3-2 )" , file=output)
        
        # Table header
        print("\n\n" , file=output)
        for w in range(weeks):
            print(f"w{w}" , file=output , end="       ")
        print(file=output)

        match = ['X','X']
        
        for p in range(periods):
            for w in range(weeks):
                for t in range(team):
                    if(z3.is_true(m[vars[t, 0, p, w]])):
                        match[1] = t+1
                    if(z3.is_true(m[vars[t, 1, p, w]])):
                        match[0] = t+1
                print(f"[{match[0]}-{match[1]}]" , file = output , end="   ")
            print(file=output)
            match = ['X','X']

    finally:
        if file_name:
            f.close()
################################# I/O FUNCTIONS #########################################



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
