import json
import sys
import os


# ========== SETTINGS VARIABLE ========== #
script_path = ''
docker_path = '/app/outputs/CP/'


# ========== HELP FUNCTIONS ========== #
return_codes = {
    0: "SAT",
    1: "❌ UNSAT",
    2: "TIME_EXCEEDED"
}


# Return code : 
# 0 -> SAT
# 1 -> UNSAT
# 2 -> TIME_EXCEEDED
def process_output_string(output_str , total_time, n_hint=None):
    lines = output_str.splitlines()
    solution_lines = []
    optimal = False
    obj_val = None
    in_solution = False
    stripped_lines = [line.strip() for line in lines]

    # If MiniZinc proves UNSAT without a solution, return empty solution
    has_solution = any(line.startswith('sol:') for line in stripped_lines)

    if "=====UNSATISFIABLE=====" in stripped_lines and not has_solution:
        return {'time': int(float(total_time)), 'optimal': True, 'obj': "None", 'sol': []}, str(n_hint), 1

    # If MiniZinc times out without a solution, return empty solution
    if "=====UNKNOWN=====" in stripped_lines and not has_solution:
        return {'time': 300, 'optimal': False, 'obj': "None", 'sol': []}, str(n_hint), 2
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith('n:'):
            n = stripped[3:]
        elif stripped.startswith('sol:'):
            in_solution = True
            sol_line = stripped[4:].strip()
            if sol_line.endswith(','):
                sol_line = sol_line[:-1].strip()
            solution_lines.append(sol_line)
        elif in_solution and stripped.startswith('['):
            if stripped.endswith(','):
                stripped = stripped[:-1].strip()
            solution_lines.append(stripped)
        elif stripped.startswith('opt:'):
            in_solution = False
            opt_str = stripped[4:].strip().lower()
            optimal = (opt_str == 'true')
        elif stripped.startswith('obj:'):
            in_solution = False
            obj_str = stripped[4:].strip()
            try:
                obj_val = int(obj_str)
            except ValueError:
                obj_val = None
        else:
            if in_solution:
                in_solution = False

    parsed_solution = []
    for s in solution_lines:
        s_corrected = s.replace('][', '],[')
        try:
            round_list = json.loads(s_corrected)
            parsed_solution.append(round_list)
        except json.JSONDecodeError as e:
            raise ValueError(f"Error parsing solution line: '{s}'. Corrected string: '{s_corrected}'") from e

    # return parsed_solution , int(total_time) , optimal , int(obj_val)

    time_value = int(float(total_time))
    if not optimal and time_value >= 299:
        time_value = 300

    new_entry = {
        'time': time_value,
        'optimal': optimal,
        'obj': int(obj_val) if obj_val is not None else None,
        'sol': parsed_solution
    }
    
    return new_entry , n , 0  # The last one is the return code

def import_raw_minizinc_output(filename='output.txt'):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        print(f"Successfully read raw solution from '{filename}'")
        return content
    except FileNotFoundError:
        print(f"File '{filename}' not found. Make sure the file exists.")
        return ""
    except PermissionError:
        print(f"Permission denied when reading '{filename}'.")
        return ""
    except Exception as e:
        print(f"Error reading file '{filename}': {e}")
        return ""
    

def import_json_solution(filename):
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"File {filename} not found. Returning empty dictionary.")
        return {}
    except Exception:
        print(f"Error during file reading. Returning empty dictionary.")
        return {}

def export_json_solution(data, filename, indent=4, compact_keys=("sol",)):
    """Pretty-print JSON, but keep inner lists in `compact_keys` compact (like [1,2])."""
    def write(obj, f, level=0, parent_key=None):
        pad = " " * (level * indent)
        if isinstance(obj, dict):
            f.write("{\n"); items = list(obj.items())
            for i, (k, v) in enumerate(items):
                f.write(pad + " " * indent + json.dumps(k) + ": ")
                write(v, f, level + 1, parent_key=k)
                if i < len(items) - 1: f.write(",\n")
            f.write("\n" + pad + "}")
        elif isinstance(obj, list):
            if parent_key in compact_keys:
                f.write("[\n")
                for i, item in enumerate(obj):
                    f.write(pad + " " * indent + json.dumps(item, separators=(",", ":")))
                    if i < len(obj) - 1: f.write(",\n")
                f.write("\n" + pad + "]")
            else:
                f.write("[\n")
                for i, item in enumerate(obj):
                    f.write(pad + " " * indent)
                    write(item, f, level + 1, parent_key=None)
                    if i < len(items) - 1: f.write(",\n")
                f.write("\n" + pad + "]")
        else:
            f.write(json.dumps(obj))

    # Make sure parent directories exist
    dirpath = os.path.dirname(filename)
    if dirpath:  # only create if not empty
        os.makedirs(dirpath, exist_ok=True)

    with open(filename, "w") as f:
        write(data, f, 0); f.write("\n")

    print(f"Successfully exported the json solution  ('{filename}')")

def add_solution_json(data , new_entry , solution_name = 'Name'):
    data[solution_name] = new_entry
    return data


# Transform the raw output from minizinc into a json structured file
if __name__ == '__main__':
    
    # Set default filename
    default_path = script_path

    if len(sys.argv) > 1:
        time = float(sys.argv[1])
        time = int(time)
    
    if len(sys.argv) > 2:
        docker_string = sys.argv[2]
        if docker_string == '--docker':
            default_path = docker_path
    
    if len(sys.argv) > 3:
        version_name = sys.argv[3]

    n_hint = None
    if len(sys.argv) > 4:
        n_hint = sys.argv[4]

    output = import_raw_minizinc_output()
    new_entry , n , return_code = process_output_string(output  , time, n_hint)

    if n is None or n == 'None':
        print(f"No solution found ({return_codes.get(return_code, 'UNKNOWN')}). Cannot export because n is unknown.")
    else:
        if(return_code != 0 ):
            print(f"No solution found ({return_codes.get(return_code, 'UNKNOWN')}). Exporting empty result entry.")
        filename = default_path + n + '.json'
        data = import_json_solution(filename)
        data = add_solution_json(data , new_entry , f'CP - {version_name}')
        export_json_solution(data , filename)
