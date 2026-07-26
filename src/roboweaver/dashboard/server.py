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

        elif path == "/api/compile":
            instruction = query.get("instruction", ["Pick up the red cube"])[0]
            compiler = SkillCompiler()
            skill = compiler.compile(instruction)
            bt_xml = export_groot2_xml(skill)
            
            res = {
                "instruction": instruction,
                "intent": {
                    "action": skill.intent.action.value,
                    "object_name": skill.intent.object_name,
                    "parameters": skill.intent.parameters,
                },
                "tasks": [
                    {"type": t.type.value, "description": t.description}
                    for t in skill.task_graph.tasks
                ],
                "behavior_tree_xml": bt_xml,
            }
            self._send_json(res)

        elif path == "/" or path == "/index.html":
            self._send_html(get_dashboard_html())

        else:
            self.send_error(404, "Not Found")

    def _send_json(self, data: Any) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # Quiet logging


def get_dashboard_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RoboWeaver Universal Robotics Control Center</title>
    <style>
        :root {
            --bg-color: #0b0f19;
            --panel-bg: rgba(19, 27, 46, 0.85);
            --accent: #8a2be2;
            --accent-light: #00f2fe;
            --text: #f8fafc;
            --muted: #94a3b8;
            --border: #1e293b;
        }
        body {
            margin: 0;
            padding: 0;
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: radial-gradient(circle at 10% 10%, #151e36, #0b0f19);
            color: var(--text);
        }
        header {
            background: linear-gradient(90deg, #131b2e, #1a233a);
            padding: 20px 36px;
            border-bottom: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 4px 20px rgba(0,0,0,0.5);
        }
        header h1 {
            margin: 0;
            font-size: 24px;
            background: linear-gradient(90deg, #38bdf8, #00f2fe, #a855f7);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .subtitle {
            color: var(--muted);
            font-size: 13px;
            margin-top: 4px;
        }
        .container {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(440px, 1fr));
            gap: 24px;
            padding: 28px;
        }
        .panel {
            background: var(--panel-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.4);
            backdrop-filter: blur(8px);
        }
        .panel h2 {
            margin-top: 0;
            font-size: 18px;
            color: #38bdf8;
            border-bottom: 1px solid var(--border);
            padding-bottom: 12px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        input, button {
            padding: 10px 14px;
            border-radius: 6px;
            border: 1px solid var(--border);
            background: #0f172a;
            color: var(--text);
            font-size: 14px;
        }
        button {
            background: linear-gradient(135deg, #3b82f6, #8b5cf6);
            color: #fff;
            font-weight: 600;
            cursor: pointer;
            border: none;
            transition: transform 0.1s, box-shadow 0.2s;
        }
        button:hover {
            transform: scale(1.02);
            box-shadow: 0 0 15px rgba(56, 189, 248, 0.4);
        }
        pre {
            background: #080d1a;
            padding: 16px;
            border-radius: 8px;
            font-size: 12px;
            overflow-x: auto;
            color: #4ade80;
            border: 1px solid #1e293b;
            line-height: 1.5;
        }
        .badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: bold;
            background: #1e293b;
            color: #38bdf8;
            margin-right: 6px;
            margin-bottom: 6px;
            border: 1px solid #334155;
        }
        .badge-cat {
            background: rgba(138, 43, 226, 0.2);
            color: #c084fc;
            border: 1px solid #7c3aed;
        }
        .pkg-card {
            background: rgba(15, 23, 42, 0.7);
            border: 1px solid #1e293b;
            border-radius: 8px;
            padding: 14px;
            margin-bottom: 12px;
        }
        .pkg-card h4 {
            margin: 0 0 6px 0;
            color: #38bdf8;
            font-size: 15px;
        }
    </style>
</head>
<body>
    <header>
        <div>
            <h1>RoboWeaver Universal Robotics Control Center</h1>
            <div class="subtitle">Universal Robotics Package & Knowledge Nexus — ROS 2 Multi-Robot Workcell Operating System</div>
        </div>
        <div>
            <span class="badge">Engine v1.0.0</span>
            <span class="badge" style="color:#4ade80; border-color:#22c55e;">Knowledge Nexus Online</span>
        </div>
    </header>

    <div class="container">
        <!-- Panel 1: Knowledge Nexus Recommendation -->
        <div class="panel" style="grid-column: 1 / -1;">
            <h2>
                <span>🧠 Universal Robotics Package & Knowledge Nexus</span>
                <span style="font-size:12px; color:#94a3b8;">Cross-Package AI Architecture Recommender</span>
            </h2>
            <div style="display:flex; gap:10px; margin-bottom:15px;">
                <input type="text" id="nexus-prompt" value="Build a visitor card scanner system with TurtleBot4 to scan security ID badges and navigate to reception desk" style="flex:1;">
                <button onclick="recommendNexus()">Recommend Architecture</button>
                <button onclick="browsePackages()" style="background: linear-gradient(135deg, #059669, #10b981);">Browse All Packages (11+)</button>
            </div>
            <div id="nexus-output">
                <pre style="color:#94a3b8;">Click 'Recommend Architecture' to analyze prompt across all ROS 2 packages, sensors, navigation stacks, and custom workspaces...</pre>
            </div>
        </div>

        <!-- Panel 2: Live Skill Compiler -->
        <div class="panel">
            <h2>⚡ Skill Compiler (NL → BehaviorTree)</h2>
            <div style="display:flex; gap:10px; margin-bottom:15px;">
                <input type="text" id="instruction" value="Pick up the red cube" style="flex:1;">
                <button onclick="compileSkill()">Compile</button>
            </div>
            <div id="compiler-output">
                <pre style="color:#94a3b8;">Click 'Compile' to generate BehaviorTree XML & Task Graph...</pre>
            </div>
        </div>

        <!-- Panel 3: Knowledge Graph -->
        <div class="panel">
            <h2>🔗 Robotics Ontology Graph (Nodes & Edges)</h2>
            <button onclick="loadKnowledge()" style="margin-bottom:15px;">Load Graph</button>
            <div id="knowledge-output">
                <pre style="color:#94a3b8;">Click 'Load Graph' to inspect Robotics Knowledge Graph Nodes & Relations...</pre>
            </div>
        </div>
    </div>

    <script>
        async function recommendNexus() {
            const prompt = document.getElementById('nexus-prompt').value;
            document.getElementById('nexus-output').innerHTML = `<pre style="color:#38bdf8;">Analyzing ecosystem packages for prompt...</pre>`;
            const res = await fetch('/api/nexus/recommend?prompt=' + encodeURIComponent(prompt));
            const data = await res.json();
            document.getElementById('nexus-output').innerHTML = `
                <div style="margin-bottom:14px;">
                    <span class="badge" style="background:#0f172a; color:#f8fafc;">Matched Robots: ${data.matched_robots.join(', ')}</span>
                </div>
                <h3 style="color:#38bdf8; margin: 12px 0 8px 0;">📦 Recommended ROS 2 Package Stack (${data.package_ids.length}):</h3>
                <div style="margin-bottom: 14px;">
                    ${data.recommended_packages.map(p => `<span class="badge badge-cat">${p}</span>`).join('')}
                </div>
                <div style="display:grid; grid-template-columns: 1fr 1fr; gap:16px;">
                    <div>
                        <h4 style="color:#38bdf8; margin-bottom:6px;">⚡ Active ROS 2 Topics</h4>
                        <pre style="max-height:160px; overflow-y:auto;">${data.ros2_topics.join('\\n') || 'None'}</pre>
                    </div>
                    <div>
                        <h4 style="color:#a855f7; margin-bottom:6px;">🎯 Active ROS 2 Actions</h4>
                        <pre style="max-height:160px; overflow-y:auto; color:#c084fc;">${data.ros2_actions.join('\\n') || 'None'}</pre>
                    </div>
                </div>
                <h4 style="color:#38bdf8; margin: 12px 0 6px 0;">📄 package.xml &lt;depend&gt; Dependencies</h4>
                <div>
                    ${data.package_xml_dependencies.map(d => `<span class="badge" style="background:#1e293b; color:#38bdf8;">${d}</span>`).join('')}
                </div>
            `;
        }

        async function browsePackages() {
            document.getElementById('nexus-output').innerHTML = `<pre style="color:#38bdf8;">Loading Universal Robotics Package Catalog...</pre>`;
            const res = await fetch('/api/nexus/packages');
            const data = await res.json();
            document.getElementById('nexus-output').innerHTML = `
                <h3 style="color:#38bdf8; margin-top:0;">📚 Cataloged Ecosystem Packages (${data.length}):</h3>
                <div style="max-height: 480px; overflow-y: auto; padding-right:8px;">
                    ${data.map(p => `
                        <div class="pkg-card">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <h4>${p.name} (<span style="color:#00f2fe;">${p.id}</span>)</h4>
                                <span class="badge badge-cat">${p.category.toUpperCase()}</span>
                            </div>
                            <p style="color:#cbd5e1; font-size:13px; margin: 6px 0;">${p.description}</p>
                            <div style="margin-top:8px;">
                                <span style="font-size:12px; color:#94a3b8;">Robots: </span>
                                ${p.compatible_robots.map(r => `<span class="badge" style="font-size:10px;">${r}</span>`).join('')}
                            </div>
                        </div>
                    `).join('')}
                </div>
            `;
        }

        async function compileSkill() {
            const inst = document.getElementById('instruction').value;
            const res = await fetch('/api/compile?instruction=' + encodeURIComponent(inst));
            const data = await res.json();
            document.getElementById('compiler-output').innerHTML = `
                <div style="margin-bottom:10px;">
                    <span class="badge">Action: ${data.intent.action}</span>
                    <span class="badge">Object: ${data.intent.object_name}</span>
                </div>
                <h3>Tasks (${data.tasks.length}):</h3>
                <ul>${data.tasks.map(t => `<li><b>${t.type}</b>: ${t.description}</li>`).join('')}</ul>
                <h3>Groot2 BehaviorTree XML:</h3>
                <pre>${escapeHtml(data.behavior_tree_xml)}</pre>
            `;
        }

        async function loadKnowledge() {
            const res = await fetch('/api/knowledge');
            const data = await res.json();
            document.getElementById('knowledge-output').innerHTML = `
                <h3>Nodes (${data.nodes.length}):</h3>
                <ul>${data.nodes.map(n => `<li><span class="badge">${n.type}</span> <b>${n.name}</b> (${n.id})</li>`).join('')}</ul>
                <h3>Relations (${data.edges.length}):</h3>
                <ul>${data.edges.map(e => `<li>${e.source_id} ──[<b>${e.relation}</b>]──▶ ${e.target_id}</li>`).join('')}</ul>
            `;
        }

        function escapeHtml(str) {
            return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        }
    </script>
</body>
</html>
"""


class ReusableHTTPServer(HTTPServer):
    allow_reuse_address = True


def start_dashboard_server(port: int = 8080) -> None:
    server_address = ("", port)
    httpd = ReusableHTTPServer(server_address, DashboardHTTPRequestHandler)
    print(f"\n\033[1;32m🚀 RoboWeaver Universal Control Center running at: http://localhost:{port}\033[0m")
    print("   Press Ctrl+C to stop server.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard server...")
        httpd.server_close()

