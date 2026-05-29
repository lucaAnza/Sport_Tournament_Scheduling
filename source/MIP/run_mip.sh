#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# MIP runner for the Sports Tournament Scheduling project
# ============================================================
#
# Interactive usage:
#   ./run_mip.sh
#
# Docker interactive usage:
#   ./run_mip.sh --docker
#
# Non-interactive usage:
#   ./run_mip.sh 6 decision
#   ./run_mip.sh 6 optimized
#   ./run_mip.sh 6 decision --docker
#   ./run_mip.sh 6 optimized --docker
#
# Run all MIP instances:
#   ./run_mip.sh all
#   ./run_mip.sh all --docker
#
# Override default instances:
#   STS_INSTANCES="6 8 10 12 14" ./run_mip.sh all
#
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"


DEFAULT_INSTANCES="2 4 6 8 10 12"
STS_INSTANCES="${STS_INSTANCES:-$DEFAULT_INSTANCES}"

docker_flag=""
positional_args=()

for arg in "$@"; do
    case "$arg" in
        --docker)
            docker_flag="--docker"
            ;;
        *)
            positional_args+=("$arg")
            ;;
    esac
done

set -- "${positional_args[@]}"


validate_team_number() {
    local team="$1"

    if ! [[ "$team" =~ ^[0-9]+$ ]]; then
        echo "Error: number of teams must be an integer."
        exit 1
    fi

    if (( team < 2 )); then
        echo "Error: number of teams must be at least 2."
        exit 1
    fi

    if (( team % 2 != 0 )); then
        echo "Error: number of teams must be even."
        exit 1
    fi
}


run_one() {
    local team="$1"
    local mode="$2"

    validate_team_number "$team"

    echo
    echo "======================================"
    echo "Running MIP: n=$team, mode=$mode"
    echo "======================================"

    cmd=("$PYTHON_BIN" "$SCRIPT_DIR/sts_milp.py" "$team")

    case "$mode" in
        decision|dec)
            ;;
        optimized|optimization|opt)
            cmd+=("--optimized")
            ;;
        *)
            echo "Error: unknown mode '$mode'."
            echo "Use one of: decision, optimized"
            exit 1
            ;;
    esac

    if [[ -n "$docker_flag" ]]; then
        cmd+=("$docker_flag")
    fi

    "${cmd[@]}"
}


run_all() {
    echo
    echo "======================================"
    echo "Running all configured MIP instances"
    echo "Instances: $STS_INSTANCES"
    echo "======================================"

    for team in $STS_INSTANCES; do
        run_one "$team" decision
        run_one "$team" optimized
    done

    echo
    echo "======================================"
    echo "Finished all MIP runs"
    echo "======================================"
}


interactive_menu() {
    while true; do
        echo
        echo "===== MIP Program Menu ====="
        echo "1. Run one MIP model"
        echo "2. Run all MIP instances"
        echo "0. EXIT"
        echo "============================"

        read -rp "Select a program to run: " choice

        case "$choice" in
            0)
                echo "Exiting..."
                break
                ;;

            1)
                read -rp "Enter number of teams, e.g. 6, 8, 10: " team
                read -rp "Do you want optimized version? (y/n): " yn

                if [[ "$yn" =~ ^[Yy](es)?$ ]]; then
                    run_one "$team" optimized
                else
                    run_one "$team" decision
                fi
                ;;

            2)
                run_all
                ;;

            *)
                echo "Invalid option. Try again."
                ;;
        esac
    done
}

