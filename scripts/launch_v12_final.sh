#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "$0")/.." && pwd)"
python_bin="$repository_root/.venv/bin/python"
rom_path="${POKEMON_RED_ROM:-}"
volume_root="${V12_VOLUME_ROOT:-}"
run_root="${V12_RUN_ROOT:-$volume_root/PokemonRedAI/v12/runs}"
dashboard_port="${V12_DASHBOARD_PORT:-8777}"
seed="${V12_SEED:-20260722}"
dry_run=false

if [[ "${1:-}" == "--dry-run" ]]; then
  dry_run=true
elif [[ $# -ne 0 ]]; then
  echo "Usage: scripts/launch_v12_final.sh [--dry-run]" >&2
  exit 2
fi

[[ -x "$python_bin" ]] || {
  echo "V12 Python environment is missing: $python_bin" >&2
  exit 1
}
[[ -n "$rom_path" && -f "$rom_path" ]] || {
  echo "Set POKEMON_RED_ROM to the private Pokemon Red ROM file before launch." >&2
  exit 1
}
[[ -n "$volume_root" ]] || {
  echo "Set V12_VOLUME_ROOT to the mounted external-storage directory before launch." >&2
  exit 1
}
[[ -d "$volume_root" ]] || {
  echo "The external SSD is not mounted at: $volume_root" >&2
  echo "Mount the declared volume before launching the fixed 48-hour experiment." >&2
  exit 1
}

free_kib="$(df -Pk "$volume_root" | awk 'NR == 2 {print $4}')"
if [[ -z "$free_kib" || "$free_kib" -lt 157286400 ]]; then
  echo "V12 requires at least 150 GiB free on the external SSD at launch." >&2
  exit 1
fi

if [[ -n "$(git -C "$repository_root" status --porcelain)" ]]; then
  echo "V12 refuses to launch from an uncommitted source tree." >&2
  exit 1
fi

if lsof -nP -iTCP:"$dashboard_port" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Dashboard port $dashboard_port is already in use." >&2
  exit 1
fi

timestamp="$(date +%Y%m%d-%H%M%S)"
run_name="v12-final-48h-$timestamp-seed$seed"
run_directory="$run_root/$run_name"
launch_log="$run_root/$run_name.launch.log"
error_log="$run_root/$run_name.launch.error.log"
pid_file="$run_root/$run_name.launch.pid"
mode_file="$run_root/$run_name.launch.mode"

command=(
  "$python_bin" -m pokemon_red_ai ppo-run
  --rom "$rom_path"
  --output "$run_directory"
  --mode self_taught_v12
  --hours 48
  --max-actions 150000000
  --seed "$seed"
  --environments 4
  --episode-actions 32768
  --rollout-steps 512
  --batch-size 256
  --epochs 4
  --learning-rate 0.00025
  --gamma 0.997
  --entropy 0.01
  --reward-scale 0.01
  --promotion-replays 3
  --checkpoint-actions 16384
  --status-seconds 2
  --narrative-minutes 60
  --port "$dashboard_port"
  --max-output-mib 102400
  --min-free-gib 50
  --frontier-probability 0.75
  --competence-window 10
  --competence-threshold 0.80
  --self-imitation-epochs 2
  --frozen-exam-interval-actions 16384
  --frozen-exam-attempts 1
  --frozen-exam-action-multiplier 2.0
  --explorer-recovery-window-actions 32
  --hindsight-max-lessons 16
  --hindsight-min-actions 8
  --hindsight-max-actions 128
  --hindsight-epochs 1
  --hindsight-contrastive-weight 0.25
  --hindsight-contrastive-margin 0.10
  --terminal-evaluation-actions 32768
)

echo "V12 fixed run: $run_directory"
echo "Dashboard: http://127.0.0.1:$dashboard_port/index.html"
echo "Seed: $seed"
echo "Budget: 48 hours; 150,000,000-action safety ceiling"
echo "Actor: one local recurrent policy; zero online LLM decisions"

if $dry_run; then
  echo "Dry run passed. The SSD, free-space, source, ROM, and port gates are ready."
  exit 0
fi

mkdir -p "$run_root"
echo "$$" >"$pid_file"
echo "terminal-foreground" >"$mode_file"

echo "Starting as a Terminal-owned foreground process with PID $$."
echo "The display may turn off; the Mac itself will remain awake while the run is active."
echo "Launcher log: $launch_log"
echo "Error log: $error_log"
echo "Keep this Terminal window open. Closing it stops the experiment."

exec /usr/bin/caffeinate -imsu "${command[@]}" >>"$launch_log" 2>>"$error_log"
