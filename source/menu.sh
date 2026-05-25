#!/bin/bash
set -euo pipefail

# Parameters
docker=${1:-}   # --docker if using Docker, empty string otherwise

# Absolute path to THIS script's folder (project root where this menu lives)
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Directories and corresponding start scripts (relative to ROOT_DIR)
declare -A scripts
scripts["SAT"]="$ROOT_DIR/SAT/start_SAT.sh"
scripts["CP"]="$ROOT_DIR/CP/start_CP.sh"
scripts["MIP"]="$ROOT_DIR/MIP/start_MIP.sh"

# Deterministic order (associative arrays are unordered)
order=("SAT" "CP" "MIP")

run_sat_all_versions_for_n() {
  local n="$1"
  echo -e "\n--- SAT | n=$n | optimized=n ---"
  printf "1\n%s\nn\n0\n" "$n" | bash "${scripts[SAT]}" "$docker"

  echo -e "\n--- SAT | n=$n | optimized=y ---"
  printf "1\n%s\ny\n0\n" "$n" | bash "${scripts[SAT]}" "$docker"
}

run_cp_all_versions_for_n() {
  local n="$1"
  # CP menu:
  # 1: Gecode (No SB)
  # 2: Chuffed (No SB)
  # 3: Gecode + SB
  # 4: Chuffed + SB
  for opt in 1 2 3 4; do
    echo -e "\n--- CP | n=$n | option=$opt ---"
    printf "%s\n%s\n0\n" "$opt" "$n" | bash "${scripts[CP]}" "$docker"
  done
}

run_mip_all_versions_for_n() {
  local n="$1"
  echo -e "\n--- MIP | n=$n | optimized=n ---"
  printf "1\n%s\nn\n0\n" "$n" | bash "${scripts[MIP]}" "$docker"

  echo -e "\n--- MIP | n=$n | optimized=y ---"
  printf "1\n%s\ny\n0\n" "$n" | bash "${scripts[MIP]}" "$docker"
}

run_all_for_range() {
  local N="$1"

  if (( N < 2 )); then
    echo "N must be >= 2"
    return 1
  fi

  # STS requires even n; enforce even upper bound
  if (( N % 2 == 1 )); then
    echo "Warning: N is odd. Using N=$((N-1)) because n must be even."
    N=$((N-1))
  fi

  for (( n=2; n<=N; n+=2 )); do
    echo -e "\n\n=============================="
    echo " Running ALL families for n=$n"
    echo "=============================="

    run_sat_all_versions_for_n "$n"
    run_cp_all_versions_for_n "$n"
    run_mip_all_versions_for_n "$n"
  done
}

# run all versions for a single specific n
run_all_for_single_n() {
  local n="$1"

  if (( n < 2 )); then
    echo "n must be >= 2"
    return 1
  fi

  # STS requires even n; enforce even n
  if (( n % 2 == 1 )); then
    echo "Warning: n is odd. Using n=$((n-1)) because n must be even."
    n=$((n-1))
  fi

  echo -e "\n\n=============================="
  echo " Running ALL families for n=$n"
  echo "=============================="

  run_sat_all_versions_for_n "$n"
  run_cp_all_versions_for_n "$n"
  run_mip_all_versions_for_n "$n"
}

while true; do
    echo -e "\n\n===== Start Menu ====="
    i=1

    # Print SAT/CP/MIP entries
    for key in "${order[@]}"; do
        echo "$i. $key"
        ((i++))
    done

    # Option: run range 2..N
    RUN_RANGE_OPTION=$i
    echo "$RUN_RANGE_OPTION. RUN ALL (SAT+CP+MIP) for n = 2..N (even only)"
    ((i++))

    # Option: run all for a specific n
    RUN_SINGLE_OPTION=$i
    echo "$RUN_SINGLE_OPTION. RUN ALL (SAT+CP+MIP) for a specific n"

    echo "0. Exit"
    echo "======================"

    read -rp "Choose a program to run (0 to exit): " choice

    if [[ "$choice" -eq 0 ]]; then
        echo "Exiting..."
        break
    elif [[ "$choice" -eq "$RUN_RANGE_OPTION" ]]; then
        read -rp "Enter max number of teams N (int): " Nmax
        run_all_for_range "$Nmax"
    elif [[ "$choice" -eq "$RUN_SINGLE_OPTION" ]]; then
        read -rp "Enter number of teams n (int, even): " n_single
        run_all_for_single_n "$n_single"
    elif (( choice >= 1 && choice <= ${#order[@]} )); then
        key="${order[$((choice-1))]}"
        script="${scripts[$key]}"
        echo "Running $key -> $script ..."
        bash "$script" "$docker"
    else
        echo "Invalid choice. Try again."
    fi
done
