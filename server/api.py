"""
server/api.py
─────────────
High-performance local backend server.
Exposes REST APIs and Server-Sent Event (SSE) streaming
for the desktop application frontend.
"""

import os
import json
import yaml
from pathlib import Path
from flask import Flask, request, Response, jsonify, send_from_directory
from core.engine import AgentEngine
from core.providers import get_provider

CFG_PATH = Path(__file__).parent.parent / "config.yaml"


def load_config() -> dict:
    if CFG_PATH.exists():
        with open(CFG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def save_config(cfg: dict):
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, default_flow_style=False, sort_keys=False)


app = Flask(__name__, static_folder="../ui/dist", static_url_path="")
config = load_config()
engine = AgentEngine(config)


@app.route("/")
def index():
    if app.static_folder and (Path(app.static_folder) / "index.html").exists():
        return send_from_directory(app.static_folder, "index.html")
    return send_from_directory(Path(__file__).parent / "static", "index.html")


@app.route("/api/config", methods=["GET"])
def get_config():
    cfg = load_config()
    return jsonify({
        "ok": True,
        "config": cfg,
        "active_provider": engine.provider_name,
        "safety_mode": engine.safety_mode,
        "workspace_roots": engine.workspace_roots,
    })


@app.route("/api/config", methods=["POST"])
def update_config():
    data = request.json or {}
    cfg = load_config()
    cfg.update(data)
    save_config(cfg)

    # Update active engine settings
    if "safety_mode" in data:
        engine.set_safety_mode(data["safety_mode"])
    if "provider" in data or "model" in data or "gemini_api_key" in data or "nvidia_api_key" in data:
        prov = data.get("provider", engine.provider_name)
        engine.set_provider(prov, cfg)
    if "workspace_roots" in data and data["workspace_roots"]:
        engine.set_workspace_root(data["workspace_roots"][0])

    return jsonify({"ok": True, "message": "Settings saved successfully", "config": cfg})


@app.route("/api/providers/test", methods=["POST"])
def test_provider():
    data = request.json or {}
    provider_name = data.get("provider", "ollama")
    test_cfg = load_config()
    test_cfg.update(data)

    try:
        prov = get_provider(provider_name, test_cfg)
        res = prov.test_connection()
        return jsonify(res)
    except Exception as e:
        return jsonify({"ok": False, "message": str(e), "models": []})


@app.route("/api/providers/models", methods=["GET"])
def get_provider_models():
    provider_name = request.args.get("provider", engine.provider_name)
    cfg = load_config()
    try:
        prov = get_provider(provider_name, cfg)
        models = prov.list_models()
        return jsonify({"ok": True, "models": models})
    except Exception as e:
        return jsonify({"ok": False, "models": [], "error": str(e)})


@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    data = request.json or {}
    prompt = data.get("prompt", "").strip()
    session_id = data.get("session_id", "")
    provider_override = data.get("provider")
    model_override = data.get("model")

    if not prompt:
        return jsonify({"ok": False, "error": "Prompt cannot be empty"}), 400

    if provider_override and provider_override != engine.provider_name:
        cfg = load_config()
        if model_override:
            cfg["model"] = model_override
        engine.set_provider(provider_override, cfg)
    elif model_override:
        engine.config["model"] = model_override
        engine.provider.model = model_override

    def generate_events():
        for event in engine.execute_stream(prompt, session_id=session_id):
            yield f"data: {json.dumps(event)}\n\n"

    return Response(generate_events(), mimetype="text/event-stream")


@app.route("/api/action/respond", methods=["POST"])
def respond_action():
    data = request.json or {}
    action_id = data.get("action_id")
    if not action_id:
        return jsonify({"ok": False, "error": "action_id is required"}), 400

    engine.submit_user_response(action_id, data)
    return jsonify({"ok": True, "action_id": action_id})


@app.route("/api/interrupt", methods=["POST"])
def interrupt_run():
    engine.interrupt()
    return jsonify({"ok": True, "message": "Interrupt requested."})


@app.route("/api/workspace/files", methods=["GET"])
def get_workspace_files():
    root = engine.workspace_roots[0] if engine.workspace_roots else os.getcwd()
    from tools.files import list_dir
    res = list_dir(root, engine.workspace_roots)
    return jsonify(res)


@app.route("/api/workspace/set", methods=["POST"])
def set_workspace():
    data = request.json or {}
    path = data.get("path")
    if not path or not Path(path).exists():
        return jsonify({"ok": False, "error": "Invalid directory path"}), 400

    engine.set_workspace_root(path)
    cfg = load_config()
    cfg["workspace_roots"] = [path]
    save_config(cfg)
    return jsonify({"ok": True, "workspace": path})


@app.route("/api/memory", methods=["GET"])
def get_memories():
    root = engine.workspace_roots[0] if engine.workspace_roots else None
    memories = engine.memory_store.list_memories(project_path=root, limit=100)
    return jsonify({"ok": True, "memories": memories})


@app.route("/api/memory/<memory_id>", methods=["DELETE"])
def delete_memory(memory_id):
    deleted = engine.memory_store.delete_memory(memory_id)
    return jsonify({"ok": deleted})


@app.route("/api/memory/clear", methods=["POST"])
def clear_memories():
    root = engine.workspace_roots[0] if engine.workspace_roots else None
    engine.memory_store.clear_memories(project_path=root)
    return jsonify({"ok": True, "message": "Memories cleared."})


def create_app():
    return app


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
