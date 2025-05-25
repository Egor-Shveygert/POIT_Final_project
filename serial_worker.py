import json
import threading
import serial
import queue
import time
from datetime import datetime
from config import SERIAL_PORT, BAUDRATE, JSON_PATH
from models import Sample, SessionLocal
import os
from models import Base, engine

# Queues for communication between Flask and worker
out_q = queue.Queue()      # from worker to Flask (WebSocket/API)
in_q = queue.Queue()       # from Flask to worker

# Global state variables
_running = None
worker_thread = None
current_ref = 512          # default regulation value
last_pwm = 512             # last measured (and sent) PWM value
recording = False
current_session_id = 0
regulating = False         # start without regulation
STOP_REF = 900

def start_recording():
    global recording, current_session_id, regulating
    current_session_id += 1
    recording = True
    regulating = True
    print(f"[recording] Start recording session_id = {current_session_id}")

def stop_recording():
    global recording, regulating
    recording = False
    regulating = False
    print("[recording] Record Stop")

def serial_thread():
    global current_ref, last_pwm, recording, regulating

    print("[serial_worker] Opening port...:", SERIAL_PORT)
    ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=0.1)
    time.sleep(2)  # let Arduino finish reset
    ser.reset_input_buffer()
    print("[serial_worker] Port open.")

    try:
        os.remove(JSON_PATH)
        print(f"[serial_worker] cleared: JSON log: {JSON_PATH}")
    except FileNotFoundError:
        pass

    # Clear DBs
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("[serial_worker] cleared: SQLite DB")

    # Clear .json's
    sess = SessionLocal()
    logf = open(JSON_PATH, "a", buffering=1)

    try:
        while _running and _running.is_set():
            # 1) Read one message (non-blocking)
            raw = ser.readline()
            if raw:
                try:
                    line = raw.decode().strip()
                    parts = line.split(",")
                    if len(parts) >= 6 and parts[0] == "L":
                        ldr = int(parts[1])
                        pwm1 = int(parts[3])
                        pwm2 = int(parts[5])

                        # update last_pwm
                        last_pwm = pwm1

                        ts_string = datetime.utcnow().isoformat(timespec="milliseconds") + "Z"
                        datum = {
                            "ts": ts_string,
                            "ldr": ldr,
                            "pwm1": pwm1,
                            "pwm2": pwm2,
                            "ref": current_ref,
                            "session_id": current_session_id
                        }

                        # Web/API
                        out_q.put(datum)

                        if recording:
                            # JSON log
                            logf.write(json.dumps(datum) + "\n")
                            # DB
                            sess.add(Sample(
                                ts=datetime.fromisoformat(ts_string.replace("Z", "")),
                                ldr=ldr,
                                pwm=pwm1,
                                ref=current_ref,
                                session_id=current_session_id
                            ))
                            sess.commit()
                    else:
                        print("[RX] Unexpeted format:", parts)
                except (UnicodeDecodeError, ValueError) as e:
                    print("[PARSE ERROR]", e, "in row:", raw)

            # 2) Process all commands from queue and decide what to send
            next_ref = None
            while True:
                try:
                    cmd = in_q.get_nowait()
                    if "start" in cmd:
                        start_recording()
                        next_ref = current_ref
                    if "stop" in cmd:
                        stop_recording()
                        # on STOP hold current PWM
                        next_ref = STOP_REF
                    if "pause" in cmd:
                        regulating = False
                    if "resume" in cmd:
                        regulating = True
                        next_ref = current_ref
                    if "ref" in cmd:
                        current_ref = cmd["ref"]
                        next_ref = current_ref
                except queue.Empty:
                    break

            # 3) Send one command S,<value> if needed
            if next_ref is not None:
                ser.write(f"S,{next_ref}\n".encode())

            # 4) Short pause to avoid 100% CPU
            time.sleep(0.05)

    except Exception as e:
        print("[serial_worker] Error in thread:", e)

    finally:
        print("[serial_worker] Closing port and recording...")
        try: ser.close()
        except: pass
        try: logf.close()
        except: pass
        try: sess.close()
        except: pass

def start_worker():
    global _running, worker_thread
    print("[start_worker] Opening thread...")

    if _running and _running.is_set():
        print("[start_worker] Thread already running — not starting again.")
        return

    _running = threading.Event()
    _running.set()
    worker_thread = threading.Thread(target=serial_thread, daemon=True)
    worker_thread.start()
    print("[start_worker] Thread open.")

def stop_worker():
    global _running, worker_thread
    print("[stop_worker] Closing thread...")

    if not _running:
        print("[stop_worker] Thread not running.")
        return

    _running.clear()
    if worker_thread:
        worker_thread.join(timeout=2)
        if worker_thread.is_alive():
            print("[stop_worker] Warning: thread still running after 2 s timeout.")
        worker_thread = None
    _running = None
    print("[stop_worker] Thread closed.")

