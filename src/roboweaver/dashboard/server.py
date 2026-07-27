"""
RoboWeaver Web Dashboard Server — serves API endpoints and interactive web control center.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from typing import Any

from roboweaver.compiler import SkillCompiler
from roboweaver.codegen.groot2 import export_groot2_xml
from roboweaver.knowledge import create_default_robotics_knowledge_graph
from roboweaver.knowledge.package_nexus import RoboticsPackageNexus
from roboweaver.registry.repository import SkillRepository
from roboweaver.hardware.registry_robots import ROBOT_REGISTRY, get_robot_spec
from roboweaver.hardware.kinematics_ndof import forward_kinematics_chain_ndof
from roboweaver.fleet.prompt_builder import SystemPromptParser, MultiRobotChoreographer
from roboweaver.simulation.inspire_sim import InspireHandSimulator
from roboweaver.hardware.inspire_hand_rs485 import InspireHandRS485Driver
from roboweaver.ir import SkillCompilationError


class DashboardHTTPRequestHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/api/knowledge":
            kg = create_default_robotics_knowledge_graph()
            self._send_json(kg.to_dict())

        elif path == "/api/nexus/packages":
            pkgs = RoboticsPackageNexus.get_all_packages()
            self._send_json([
                {
                    "id": p.id,
                    "name": p.name,
                    "category": p.category,
                    "description": p.description,
                    "compatible_robots": p.compatible_robots,
                    "ros2_dependencies": p.ros2_dependencies,
                    "default_topics": p.default_topics,
                    "default_actions": p.default_actions,
                    "version": p.version,
                }
                for p in pkgs
            ])

        elif path == "/api/nexus/recommend":
            prompt = query.get("prompt", ["Build ShopMate-R retail assistant with Temi, Pepper, and Franka"])[0]
            rec = RoboticsPackageNexus.recommend_stack_for_prompt(prompt)
            self._send_json(rec)

        elif path == "/api/skills":
            repo = SkillRepository()
            pkgs = repo.list_packages()
            self._send_json([
                {
                    "id": p.id,
                    "name": p.name,
                    "version": p.version,
                    "action": p.action,
                    "target_object": p.target_object,
                    "description": p.description,
                }
                for p in pkgs
            ])

        elif path == "/api/robots":
            seen: set[str] = set()
            robots = []
            for spec in ROBOT_REGISTRY.values():
                if spec.id in seen:
                    continue
                seen.add(spec.id)
                robots.append({
                    "id": spec.id,
                    "name": spec.name,
                    "manufacturer": spec.manufacturer,
                    "dof": spec.dof,
                    "payload_capacity_kg": spec.payload_capacity_kg,
                    "max_reach_m": spec.max_reach_m,
                    "gripper_type": spec.gripper_type,
                    "description": spec.description,
                })
            self._send_json(robots)

        elif path.startswith("/api/robots/") and path.endswith("/model"):
            robot_id = path[len("/api/robots/"):-len("/model")]
            spec = get_robot_spec(robot_id)
            self._send_json({
                "id": spec.id,
                "name": spec.name,
                "dof": spec.dof,
                "base_height_m": spec.base_height_m,
                "max_reach_m": spec.max_reach_m,
                "joints": [
                    {
                        "name": j.name,
                        "type": j.type,
                        "axis": list(j.axis),
                        "lower_limit": j.lower_limit,
                        "upper_limit": j.upper_limit,
                    }
                    for j in spec.joints
                ],
                "links": [{"name": l.name, "length": l.length, "mass": l.mass} for l in spec.links],
            })

        elif path.startswith("/api/robots/") and path.endswith("/fk"):
            robot_id = path[len("/api/robots/"):-len("/fk")]
            spec = get_robot_spec(robot_id)
            q_param = query.get("q", [""])[0]
            if q_param:
                try:
                    q = [float(v) for v in q_param.split(",")]
                except ValueError:
                    self.send_error(400, "q must be a comma-separated list of numbers")
                    return
            else:
                q = [0.0] * spec.dof
            positions = forward_kinematics_chain_ndof(spec, q)
            self._send_json({
                "id": spec.id,
                "q": q,
                # Real forward-kinematics chain -- the exact function the compiler's
                # motion planner uses -- not a client-side approximation.
                "positions": [[p.x, p.y, p.z] for p in positions],
            })

        elif path == "/api/build":
            prompt = query.get(
                "prompt",
                ["Build ShopMate-R retail assistant with Temi for navigation, Pepper for customer interaction, and Franka arm for restocking"],
            )[0]

            parsed = SystemPromptParser.parse(prompt)
            choreographer = MultiRobotChoreographer(workcell_name=parsed.workcell_name)
            for t in parsed.tasks:
                choreographer.add_robot_task(
                    step_id=t["step_id"],
                    robot_id=t["robot_id"],
                    instruction=t["instruction"],
                    depends_on=t["depends_on"],
                    handover_target=t["handover_target"],
                )
            schedule = choreographer.compile_workcell(verbose=False)
            tiers = schedule.get_execution_tiers()
            bt_xml = choreographer.generate_composite_behavior_tree()

            res = {
                "prompt": prompt,
                "workcell_name": parsed.workcell_name,
                "robots": parsed.robots,
                "tiers": [
                    [
                        {
                            "step_id": s.step_id,
                            "robot_id": s.robot_id,
                            "instruction": s.instruction,
                            "depends_on": s.depends_on,
                            "handover_target": s.handover_target,
                            "action": s.compiled_skill.intent.action.value if s.compiled_skill else None,
                        }
                        for s in tier
                    ]
                    for tier in tiers
                ],
                "behavior_tree_xml": bt_xml,
            }
            self._send_json(res)

        elif path == "/api/simulate/gestures":
            self._send_json(list(InspireHandRS485Driver.GESTURES.keys()))

        elif path == "/api/simulate/objects":
            self._send_json([
                {
                    "id": key,
                    "name": obj.name,
                    "diameter_mm": obj.diameter_mm,
                    "compatible_gestures": obj.compatible_gestures,
                    "min_hold_force_n": obj.min_hold_force_n,
                    "max_safe_force_n": obj.max_safe_force_n,
                }
                for key, obj in InspireHandSimulator.OBJECT_CATALOG.items()
            ])

        elif path == "/api/simulate":
            gesture = query.get("gesture", ["open"])[0]
            object_key = query.get("object", ["medical_vial"])[0]

            if gesture not in InspireHandRS485Driver.GESTURES:
                self.send_error(400, f"Unknown gesture '{gesture}'")
                return
            if object_key not in InspireHandSimulator.OBJECT_CATALOG:
                self.send_error(400, f"Unknown object '{object_key}'")
                return

            sim = InspireHandSimulator()
            sim.load_object(object_key)
            sim.driver.set_gesture(gesture)
            for _ in range(5):
                state = sim.step(dt=0.05)

            total_force = round(sum(state.actuator_forces_n), 2)
            res = {
                "gesture": state.gesture_active,
                "object": object_key,
                "is_simulated": sim.driver.simulated,
                "connect_fallback_reason": sim.driver.last_connect_error,
                "actuator_positions": state.actuator_positions,
                "actuator_currents_ma": state.actuator_currents_ma,
                "actuator_forces_n": state.actuator_forces_n,
                "total_force_n": total_force,
                "object_name": sim.current_object.name if sim.current_object else None,
                "object_status": sim.current_object.status if sim.current_object else "NO OBJECT LOADED",
                "stability_score": round(sim.stability_score, 2),
                "slip_risk": sim.current_object.slip_risk if sim.current_object else 0.0,
            }
            self._send_json(res)

        elif path == "/api/compile":
            instruction = query.get("instruction", ["Pick up the red cube"])[0]
            robot_id = query.get("robot", ["franka_panda"])[0]

            compiler = SkillCompiler(target_robot=robot_id)
            try:
                result = compiler.compile_with_diagnostics(instruction, verbose=False)
            except SkillCompilationError as exc:
                self._send_json(
                    {
                        "error": "compilation_failed",
                        "diagnostics": [d.to_dict() for d in exc.diagnostics],
                    },
                    status=400,
                )
                return

            bt_xml = export_groot2_xml(result.skill)

            res = {
                "instruction": instruction,
                "robot": robot_id,
                "intent": {
                    "action": result.skill.intent.action.value,
                    "object_name": result.skill.intent.object_name,
                    "parameters": result.skill.intent.parameters,
                },
                "tasks": [
                    {"type": t.type.value, "description": t.description}
                    for t in result.skill.task_graph.tasks
                ],
                "behavior_tree_xml": bt_xml,
                "ir": result.ir.to_dict(),
                "diagnostics": [d.to_dict() for d in result.diagnostics],
            }
            self._send_json(res)

        elif path == "/" or path == "/index.html":
            self._send_json(
                {
                    "message": "RoboWeaver API server. The web UI is the Next.js frontend.",
                    "frontend": "cd frontend && npm run dev  ->  http://localhost:3000",
                    "api_docs": "See docs/REDESIGN.md for the API surface.",
                }
            )

        else:
            self.send_error(404, "Not Found")

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # Quiet logging


class ReusableHTTPServer(HTTPServer):
    allow_reuse_address = True


def start_dashboard_server(port: int = 8080) -> None:
    server_address = ("", port)
    httpd = ReusableHTTPServer(server_address, DashboardHTTPRequestHandler)
    print(f"\n\033[1;32m🚀 RoboWeaver API server running at: http://localhost:{port}\033[0m")
    print(f"   Frontend (Engineering Workbench): cd frontend && npm run dev -> http://localhost:3000")
    print("   Press Ctrl+C to stop server.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard server...")
        httpd.server_close()

