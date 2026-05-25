#!/usr/bin/env bash

set -euo pipefail

# Parameters
docker=${1:-}     # --docker if using Docker, empty string otherwise

# Absolute path to THIS script's folder (e.g., .../SAT)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# List of Python programs (put them in the same folder as this script)
programs=(
  "$SCRIPT_DIR/SAT1_pairwise.py"
  "$SCRIPT_DIR/SAT1_heule.py"
  "$SCRIPT_DIR/SAT1_bitwise.py"
  "$SCRIPT_DIR/SAT1_sequential.py"
  "$SCRIPT_DIR/SAT2.py"
)

while true; do
    echo -e "\n===== Program Menu ====="
    echo "1. RUN TEST ON ALL VERSIONS (it uses best possible settings, including precomputing)"
    for i in "${!programs[@]}"; do
        echo "$((i+2)). $(basename "${programs[$i]}")"
    done
    echo "0. EXIT "
    echo "========================"

    read -rp "Select a program to run (0 to exit): " choice

    if [[ "$choice" == "0" ]]; then
        echo "Exiting..."
        break
    elif [[ "$choice" == "1" ]]; then
        # Ask parameters
        read -rp "Enter number of teams (int): " team
        read -rp "Do you want optimized version? (y/n): " yn

        # Run all programs with parameters
        for prog in "${programs[@]}"; do
            if [[ -f "$prog" ]]; then
                if [ $yn == "y" ]; then
                    python3 "$prog" "$team" "--optimized" "$docker" "--precomputing"
                else
                    python3 "$prog" "$team" "$docker" "--precomputing"
                fi
                
            else
                echo "Error: file not found -> $prog"
            fi
        done
    # Run onlt the selected program
    elif [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 2 && choice <= ${#programs[@]}+1 )); then
        prog="${programs[$((choice-2))]}"
        if [[ -f "$prog" ]]; then
            echo "Starting $(basename "$prog")..."
            python3 "$prog" "$docker"
        else
            echo "Error: file not found -> $prog"
        fi
    else
        echo "Invalid option. Try again."
    fi
done
