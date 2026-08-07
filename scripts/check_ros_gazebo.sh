#!/usr/bin/env bash
set -euo pipefail

model_path="${1:-}"
if [[ -z "${model_path}" || ! -f "${model_path}" ]]; then
  echo "usage: scripts/check_ros_gazebo.sh /absolute/path/to/model.urdf" >&2
  exit 2
fi

for command_name in ros2 gz check_urdf timeout; do
  command -v "${command_name}" >/dev/null || {
    echo "missing required command: ${command_name}" >&2
    exit 3
  }
done

check_urdf "${model_path}"
run_dir="$(mktemp -d)"
gazebo_pid=""
cleanup() {
  if [[ -n "${gazebo_pid}" ]]; then kill "${gazebo_pid}" 2>/dev/null || true; fi
  rm -rf "${run_dir}"
}
trap cleanup EXIT

ros2 launch ros_gz_sim gz_sim.launch.py gz_args:="-s -r empty.sdf -v 2" \
  >"${run_dir}/gazebo.log" 2>&1 &
gazebo_pid=$!

ready=0
for _ in $(seq 1 30); do
  if gz service -l 2>/dev/null | grep -q '/world/empty/create'; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "${ready}" != "1" ]]; then
  echo "Gazebo create service did not become ready" >&2
  tail -100 "${run_dir}/gazebo.log" >&2
  exit 4
fi

timeout 30 ros2 run ros_gz_sim create \
  -world empty -file "${model_path}" -name roboweaver_ci_robot -z 0.05
timeout 20 gz model --list | tee "${run_dir}/models.txt"
grep -q 'roboweaver_ci_robot' "${run_dir}/models.txt"
timeout 20 gz model -m roboweaver_ci_robot | tee "${run_dir}/model.txt"
for joint_index in $(seq 1 7); do
  grep -q "Name: panda_joint${joint_index}" "${run_dir}/model.txt"
done
echo "ROS 2 / Gazebo acceptance passed: URDF parsed, spawned, and exposed its joints."
