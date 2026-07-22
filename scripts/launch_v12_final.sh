#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "$0")/.." && pwd)"
python_bin="$repository_root/.venv/bin/python"
rom_path="${POKEMON_RED_ROM:-}"
volume_root="${V12_VOLUME_ROOT:-/Volumes/T7 Developer}"
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
[[ -d "$volume_root" ]] || {
  echo "The external SSD is not mounted at: $volume_root" >&2
  echo "Mount the T7 before launching the fixed 48-hour experiment." >&2
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
label_file="$run_root/$run_name.launch.label"
launch_agent="$run_root/$run_name.launchd.plist"
launch_label="com.pokemonredai.v12.$timestamp"

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
launch_arguments=(/usr/bin/caffeinate -imsu "${command[@]}")

/usr/bin/plutil -create xml1 "$launch_agent"
/usr/bin/plutil -insert Label -string "$launch_label" "$launch_agent"
/usr/bin/plutil -insert ProgramArguments -xml '<array/>' "$launch_agent"
for argument_index in "${!launch_arguments[@]}"; do
  /usr/bin/plutil -insert "ProgramArguments.$argument_index" \
    -string "${launch_arguments[$argument_index]}" "$launch_agent"
done
/usr/bin/plutil -insert RunAtLoad -bool true "$launch_agent"
/usr/bin/plutil -insert KeepAlive -bool false "$launch_agent"
/usr/bin/plutil -insert ProcessType -string Background "$launch_agent"
/usr/bin/plutil -insert StandardOutPath -string "$launch_log" "$launch_agent"
/usr/bin/plutil -insert StandardErrorPath -string "$error_log" "$launch_agent"

launch_domain="gui/$(id -u)"
launchctl bootstrap "$launch_domain" "$launch_agent"
echo "$launch_label" >"$label_file"

sleep 1
launch_receipt="$(launchctl print "$launch_domain/$launch_label")"
launcher_pid="$(awk '/pid =/ {print $3; exit}' <<<"$launch_receipt")"
if [[ -z "$launcher_pid" ]]; then
  echo "The macOS launch job did not remain alive. Inspect: $error_log" >&2
  exit 1
fi
echo "$launcher_pid" >"$pid_file"

echo "Launched as macOS job $launch_label with PID $launcher_pid."
echo "The display may turn off; the Mac itself will remain awake while the run is active."
echo "Launcher log: $launch_log"
echo "Error log: $error_log"
echo "Stop command: launchctl bootout $launch_domain/$launch_label"
