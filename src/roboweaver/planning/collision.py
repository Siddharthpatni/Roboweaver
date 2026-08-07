"""Bounded environment collision checking and deterministic replanning."""

from __future__ import annotations

import dataclasses
import heapq
import math
from itertools import count

from roboweaver.hardware.kinematics_ndof import forward_kinematics_chain_ndof
from roboweaver.hardware.robot_spec import RobotSpec
from roboweaver.math3d import Vec3
from roboweaver.optimize.motion_cache import generate_min_jerk_traj, min_safe_duration
from roboweaver.planning.scene import Scene
from roboweaver.types import MotionPlan, MotionSegment


class CollisionPlanningError(ValueError):
    """No collision-free path was found within the planner's declared bound."""


class CollisionAwarePlanner:
    """Check every emitted waypoint and deterministically repair colliding paths.

    Serial arms use bounded joint-space midpoint search and complete link-capsule
    checks at each sampled waypoint.  Mobile bases use an 8-connected A* occupancy
    grid with obstacle inflation equal to the declared base radius.
    """

    def __init__(self, spec: RobotSpec, scene: Scene, *, max_joint_candidates: int = 96):
        if scene.frame_id != "robot_base":
            raise CollisionPlanningError(
                f"scene frame {scene.frame_id!r} must be transformed to 'robot_base' before planning"
            )
        self.spec = spec
        self.scene = scene
        self.max_joint_candidates = max_joint_candidates

    def replan(self, plan: MotionPlan) -> MotionPlan:
        if not self.scene.obstacles:
            return dataclasses.replace(
                plan, collision_checked=True, scene_digest=self.scene.digest(),
            )
        if self.spec.motion_model in {"serial_arm", "branched_humanoid"}:
            trajectories = self._replan_joint_trajectories(plan)
        elif self.spec.motion_model in {"holonomic_base", "differential_drive"}:
            trajectories = self._replan_mobile_trajectories(plan)
        elif self.spec.motion_model == "multi_finger_hand":
            # A standalone hand has no translational pose in RobotSpec. Claiming an
            # environment check here would hide the missing parent-arm transform.
            raise CollisionPlanningError(
                "multi_finger_hand requires a parent-arm/workcell transform for environment planning"
            )
        else:
            raise CollisionPlanningError(
                f"no collision planner registered for {self.spec.motion_model!r}"
            )
        return dataclasses.replace(
            plan,
            trajectories=trajectories,
            collision_checked=True,
            scene_digest=self.scene.digest(),
        )

    def _replan_joint_trajectories(self, plan: MotionPlan) -> dict[str, MotionSegment]:
        output: dict[str, MotionSegment] = {}
        for name, segment in plan.trajectories.items():
            if self._joint_path_clear(segment.waypoints):
                output[name] = segment
                continue
            replacement = self._joint_detour(segment)
            if replacement is None:
                raise CollisionPlanningError(
                    f"no collision-free joint path for {name!r} after "
                    f"{self.max_joint_candidates} deterministic candidates"
                )
            output[name] = replacement
        return output

    def _joint_path_clear(self, waypoints) -> bool:
        for configuration in waypoints:
            for points in self._configuration_chains(configuration):
                for start, end in zip(points, points[1:]):
                    # Bounded capsule sampling. Resolution is explicit in Scene and
                    # each point is inflated by the declared link radius.
                    distance = (end - start).norm()
                    samples = max(2, math.ceil(distance / self.scene.resolution_m))
                    for index in range(samples + 1):
                        t = index / samples
                        point = start + (end - start) * t
                        if self.scene.collides(point, self.spec.collision_radius_m):
                            return False
        return True

    def _configuration_chains(self, configuration) -> list[list[Vec3]]:
        if self.spec.motion_model != "branched_humanoid":
            return [forward_kinematics_chain_ndof(self.spec, configuration)]
        chains: list[list[Vec3]] = []
        for name, indices in self.spec.kinematic_chains.items():
            if name == "head":
                continue
            chain_spec = dataclasses.replace(
                self.spec,
                id=f"{self.spec.id}:{name}",
                dof=len(indices),
                joints=[self.spec.joints[index] for index in indices],
                links=[self.spec.links[index] for index in indices],
                base_height_m=self.spec.motion_parameters["branch_base_height_m"],
                motion_model="serial_arm",
                kinematic_chains={},
                motion_parameters={},
            )
            chains.append(
                forward_kinematics_chain_ndof(
                    chain_spec, [configuration[index] for index in indices],
                )
            )
        return chains

    def _joint_detour(self, segment: MotionSegment) -> MotionSegment | None:
        start, end = list(segment.start_pose), list(segment.end_pose)
        limits = self.spec.get_joint_limits()
        for candidate_index in range(self.max_joint_candidates):
            midpoint: list[float] = []
            for joint_index, (lo, hi) in enumerate(limits[: self.spec.dof]):
                center = (start[joint_index] + end[joint_index]) / 2.0
                direction = 1.0 if ((candidate_index + joint_index) % 2 == 0) else -1.0
                ring = 1 + candidate_index // max(1, 2 * self.spec.dof)
                offset = direction * min(0.45, 0.08 * ring) * (hi - lo)
                midpoint.append(max(lo, min(hi, center + offset)))
            first = generate_min_jerk_traj(start, midpoint, 35)
            second = generate_min_jerk_traj(midpoint, end, 35)[1:]
            candidate = first + second
            if self._joint_path_clear(candidate):
                duration = (
                    min_safe_duration(self.spec, start, midpoint, 0.3)
                    + min_safe_duration(self.spec, midpoint, end, 0.3)
                )
                return MotionSegment(start, end, candidate, duration)
        return None

    def _replan_mobile_trajectories(self, plan: MotionPlan) -> dict[str, MotionSegment]:
        output: dict[str, MotionSegment] = {}
        world_start = (0.0, 0.0)
        for name, segment in plan.trajectories.items():
            solution = plan.ik_results[name]
            world_goal = (float(solution.target_pos[0]), float(solution.target_pos[1]))
            route = self._astar(world_start, world_goal)
            if self.spec.motion_model == "holonomic_base":
                waypoints = []
                for index, (x, y) in enumerate(route):
                    if index + 1 < len(route):
                        nx, ny = route[index + 1]
                        theta = math.atan2(ny - y, nx - x)
                    elif waypoints:
                        theta = waypoints[-1][2]
                    else:
                        theta = 0.0
                    waypoints.append([x, y, theta])
                start_q, end_q = waypoints[0], waypoints[-1]
            else:
                waypoints = self._route_to_wheels(route, list(segment.start_pose))
                start_q, end_q = waypoints[0], waypoints[-1]
                solution.joint_angles = end_q
            duration = self._path_safe_duration(waypoints, segment.duration)
            output[name] = MotionSegment(start_q, end_q, waypoints, duration)
            world_start = world_goal
        return output

    def _path_safe_duration(self, waypoints: list[list[float]], default: float) -> float:
        """Duration for a uniformly timed polyline respecting every joint limit."""
        if len(waypoints) < 2:
            return default
        required_step = 0.0
        velocities = self.spec.get_max_velocities()
        for first, second in zip(waypoints, waypoints[1:]):
            for index, limit in enumerate(velocities[: self.spec.dof]):
                if limit > 0:
                    # Same min-jerk peak and 10% margin as motion_cache.
                    required_step = max(
                        required_step,
                        1.875 * abs(second[index] - first[index]) / limit * 1.1,
                    )
        return max(default, required_step * (len(waypoints) - 1))

    def _route_to_wheels(self, route: list[tuple[float, float]], start_wheels: list[float]) -> list[list[float]]:
        radius = self.spec.motion_parameters["wheel_radius_m"]
        track = self.spec.motion_parameters["track_width_m"]
        wheels = list(start_wheels)
        heading = 0.0
        output = [list(wheels)]
        for (x0, y0), (x1, y1) in zip(route, route[1:]):
            next_heading = math.atan2(y1 - y0, x1 - x0)
            turn = (next_heading - heading + math.pi) % (2 * math.pi) - math.pi
            distance = math.hypot(x1 - x0, y1 - y0)
            wheels[0] += distance / radius - turn * track / (2 * radius)
            wheels[1] += distance / radius + turn * track / (2 * radius)
            output.append(list(wheels))
            heading = next_heading
        return output

    def _astar(self, start: tuple[float, float], goal: tuple[float, float]) -> list[tuple[float, float]]:
        resolution = self.scene.resolution_m
        to_cell = lambda point: (round(point[0] / resolution), round(point[1] / resolution))
        start_cell, goal_cell = to_cell(start), to_cell(goal)
        padding = max(8, math.ceil(1.0 / resolution))
        min_x = min(start_cell[0], goal_cell[0]) - padding
        max_x = max(start_cell[0], goal_cell[0]) + padding
        min_y = min(start_cell[1], goal_cell[1]) - padding
        max_y = max(start_cell[1], goal_cell[1]) + padding

        def blocked(cell: tuple[int, int]) -> bool:
            point = Vec3(cell[0] * resolution, cell[1] * resolution, self.spec.base_height_m)
            return self.scene.collides(point, self.spec.collision_radius_m)

        if blocked(start_cell) or blocked(goal_cell):
            raise CollisionPlanningError("mobile start or goal lies inside inflated collision geometry")
        frontier: list[tuple[float, int, tuple[int, int]]] = []
        sequence = count()
        heapq.heappush(frontier, (0.0, next(sequence), start_cell))
        came_from: dict[tuple[int, int], tuple[int, int] | None] = {start_cell: None}
        cost = {start_cell: 0.0}
        neighbors = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))
        while frontier:
            _, _, current = heapq.heappop(frontier)
            if current == goal_cell:
                break
            for dx, dy in neighbors:
                nxt = (current[0] + dx, current[1] + dy)
                if not (min_x <= nxt[0] <= max_x and min_y <= nxt[1] <= max_y) or blocked(nxt):
                    continue
                new_cost = cost[current] + math.hypot(dx, dy)
                if new_cost < cost.get(nxt, float("inf")):
                    cost[nxt] = new_cost
                    priority = new_cost + math.hypot(goal_cell[0] - nxt[0], goal_cell[1] - nxt[1])
                    heapq.heappush(frontier, (priority, next(sequence), nxt))
                    came_from[nxt] = current
        if goal_cell not in came_from:
            raise CollisionPlanningError("A* exhausted the bounded mobile planning grid")
        cells = []
        current: tuple[int, int] | None = goal_cell
        while current is not None:
            cells.append(current)
            current = came_from[current]
        cells.reverse()
        route = [(cell[0] * resolution, cell[1] * resolution) for cell in cells]
        route[0], route[-1] = start, goal
        return route
