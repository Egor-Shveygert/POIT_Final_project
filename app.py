# app.py
from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
import serial_worker  # import module to sync current_ref
from serial_worker import start_worker, stop_worker, out_q, in_q
from models import SessionLocal, Sample
from sqlalchemy import select
import json, pathlib, os, threading
from config import JSON_PATH


print("== app.py sa naozaj spustil ==")

app = Flask(__name__, static_folder="static")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

state = "idle"      # "open" | "running" | "stopped" | "closed"

@app.route("/open", methods=["POST"])
def open_route():
    print("[/open] Požiadavka prijatá")
    global state
    if state != "open":
        start_worker()
        state = "open"
    return "OK"

@app.route("/params", methods=["POST"])
def params_route():
    """nastavenie novej ref hodnoty a broadcast klientom"""
    data = request.json
    new_ref = int(data.get("ref", 512))
    # send command to worker and update its internal target
    in_q.put({"ref": new_ref})
    # also sync module variable
    serial_worker.current_ref = new_ref
    # notify all clients of new target
    socketio.emit("ref_update", {"ref": new_ref})
    return "OK"

@app.route("/start", methods=["POST"])
def start_route():
    global state
    in_q.put({"start": True})
    in_q.put({"resume": True})
    state = "running"
    return "OK"

@app.route("/stop", methods=["POST"])
def stop_route():
    global state
    in_q.put({"stop": True})
    in_q.put({"pause": True})
    #in_q.put({"ref": 0})
    import serial_worker
    #serial_worker.current_ref = 0
    #socketio.emit("ref_update", {"ref": 0})
    state = "stopped"
    return "OK"

@app.route("/close", methods=["POST"])
def close_route():
    global state
    #in_q.put({"stop": True})
    stop_worker()
    state = "closed"
    return "OK"

@app.route("/history/db")
def history_db():
    N = int(request.args.get("n", 200))
    sess = SessionLocal()
    rows = sess.scalars(select(Sample).order_by(Sample.ts.desc()).limit(N))
    return jsonify([r.__dict__ for r in rows][::-1])

@app.route("/history/json")
def history_json():
    N = int(request.args.get("n", 200))
    lines = pathlib.Path("data/logs.json").read_text().splitlines()[-N:]
    return "[" + ",".join(lines) + "]"

# --- SocketIO realtime push ---
@socketio.on("connect")
def sock_connect():
    emit("state", {"state": state})
    emit("ref_update", {"ref": serial_worker.current_ref})


def forward_thread():
    while True:
        data = out_q.get()
        #print("[EMITUJEM SAMPLE]", data)
        socketio.emit("sample", data)

threading.Thread(target=forward_thread, daemon=True).start()

# SPA fallback
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_spa(path):
    if path and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, "index.html")


from flask import jsonify
from models import SessionLocal, Sample
import os, json

@app.route("/sessions/db")
def get_db_sessions():
    sess = SessionLocal()
    ids = sess.query(Sample.session_id).distinct().order_by(Sample.session_id).all()
    return jsonify([id[0] for id in ids if id[0] is not None])

@app.route("/sessions/json")
def get_json_sessions():
    ids = set()
    if os.path.exists(JSON_PATH):
        with open(JSON_PATH) as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    ids.add(rec.get("session_id", 0))
                except:
                    pass
    return jsonify(sorted(list(ids)))

@app.route("/session/db/<int:sid>")
def get_db_session_data(sid):
    sess = SessionLocal()
    samples = sess.query(Sample).filter_by(session_id=sid).order_by(Sample.ts).all()
    return jsonify([{
        "ts": s.ts.isoformat(timespec="milliseconds") + "Z",
        "ldr": s.ldr,
        "pwm": s.pwm,
        "ref": s.ref
    } for s in samples])

@app.route("/session/json/<int:sid>")
def get_json_session_data(sid):
    data = []
    if os.path.exists(JSON_PATH):
        with open(JSON_PATH) as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    if rec.get("session_id") == sid:
                        data.append(rec)
                except:
                    pass
    return jsonify(data)


if __name__ == "__main__":
    print("spustam socketio.run...")
    socketio.run(app, host="0.0.0.0", port=5000)


