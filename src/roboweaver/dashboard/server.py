"""
RoboWeaver Web Dashboard Server — serves API endpoints and interactive web control center.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from roboweaver.compiler import SkillCompiler
from roboweaver.codegen.groot2 import export_groot2_xml
from roboweaver.knowledge import create_default_robotics_knowledge_graph
from roboweaver.registry.repository import SkillRepository


class DashboardHTTPRequestHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/api/knowledge":
            kg = create_default_robotics_knowledge_graph()
            self._send_json(kg.to_dict())

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
    <title>RoboWeaver Developer Dashboard</title>
    <style>
        :root {
            --bg-color: #0b0f19;
            --panel-bg: #131b2e;
            --accent: #8a2be2;
            --accent-light: #00f2fe;
            --text: #e2e8f0;
            --muted: #64748b;
            --border: #1e293b;
        }
        body {
            margin: 0;
            padding: 0;
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: var(--bg-color);
            color: var(--text);
        }
        header {
            background: linear-gradient(90deg, #131b2e, #1a233a);
            padding: 16px 32px;
            border-bottom: 1fr solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        header h1 {
            margin: 0;
            font-size: 22px;
            background: linear-gradient(90deg, #4facfe, #00f2fe);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .subtitle {
            color: var(--muted);
            font-size: 13px;
        }
        .container {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            padding: 24px;
        }
        .panel {
            background: var(--panel-bg);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        }
        .panel h2 {
            margin-top: 0;
            font-size: 16px;
            color: #38bdf8;
            border-bottom: 1px solid var(--border);
            padding-bottom: 10px;
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
            transition: transform 0.1s;
        }
        button:hover {
            transform: scale(1.02);
        }
        pre {
            background: #080d1a;
            padding: 14px;
            border-radius: 6px;
            font-size: 12px;
            overflow-x: auto;
            color: #4ade80;
            border: 1px solid #1e293b;
        }
        .badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: bold;
            background: #1e293b;
            color: #38bdf8;
            margin-right: 6px;
        }
    </style>
</head>
<body>
    <header>
        <div>
            <h1>RoboWeaver Control Center</h1>
            <div class="subtitle">Compile Robotics Knowledge into Executable Intelligence</div>
        </div>
        <div>
            <span class="badge">Engine v0.1.0</span>
            <span class="badge" style="color:#4ade80;">System Active</span>
        </div>
    </header>

    <div class="container">
        <!-- Panel 1: Live Compiler -->
        <div class="panel">
            <h2>Skill Compiler (NL → BehaviorTree)</h2>
            <div style="display:flex; gap:10px; margin-bottom:15px;">
                <input type="text" id="instruction" value="Pick up the red cube" style="flex:1;">
                <button onclick="compileSkill()">Compile</button>
            </div>
            <div id="compiler-output">
                <pre>Click 'Compile' to generate BehaviorTree XML & Task Graph...</pre>
            </div>
        </div>

        <!-- Panel 2: Knowledge Graph -->
        <div class="panel">
            <h2>Robotics Knowledge Graph</h2>
            <button onclick="loadKnowledge()" style="margin-bottom:15px;">Load Graph</button>
            <div id="knowledge-output">
                <pre>Click 'Load Graph' to inspect Robotics Knowledge Graph Nodes & Relations...</pre>
            </div>
        </div>
    </div>

    <script>
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


def start_dashboard_server(port: int = 8080) -> None:
    server_address = ("", port)
    httpd = HTTPServer(server_address, DashboardHTTPRequestHandler)
    print(f"\n\033[1;32m🚀 RoboWeaver Web Dashboard running at: http://localhost:{port}\033[0m")
    print("   Press Ctrl+C to stop server.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard server...")
        httpd.server_close()
