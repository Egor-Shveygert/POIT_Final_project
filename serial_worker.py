

# serial_worker.py

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

# Fronty na komunikáciu medzi Flaskom a workerom
out_q = queue.Queue()      # z workeru do Flasku (WebSocket/API)
in_q = queue.Queue()       # z Flasku do workeru

# Stavové globálne premenné
_running = None
worker_thread = None
current_ref = 512          # predvolená regulačná hodnota
last_pwm = 512             # naposledy meraná (a vyslaná) PWM hodnota
recording = False
current_session_id = 0
regulating = False         # štartujeme bez regulácie
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
    time.sleep(2)  # nech Arduino dokončí reštart
    ser.reset_input_buffer()
    print("[serial_worker] Port oped.")

    try:
        os.remove(JSON_PATH)
        print(f"[serial_worker] cleared: JSON log: {JSON_PATH}")
    except FileNotFoundError:
        pass

    #clear DBs
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("[serial_worker] cleared: SQLite DB")

    #clear .json's
    sess = SessionLocal()
    logf = open(JSON_PATH, "a", buffering=1)

    try:
        while _running and _running.is_set():
            # 1) Prečítaj jednorazovo jednu správu (non-blokujúco)
            raw = ser.readline()
            if raw:
                try:
                    line = raw.decode().strip()
                    parts = line.split(",")
                    if len(parts) >= 6 and parts[0] == "L":
                        ldr = int(parts[1])
                        pwm1 = int(parts[3])
                        pwm2 = int(parts[5])

                        # aktualizuj last_pwm
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

            # 2) Spracuj všetky príkazy z fronty a rozhodni, čo poslať
            next_ref = None
            while True:
                try:
                    cmd = in_q.get_nowait()
                    if "start" in cmd:
                        start_recording()
                        next_ref = current_ref
                    if "stop" in cmd:
                        stop_recording()
                        # pri STOP držíme current PWM
                        next_ref = STOP_REF
                        #next_ref = current_ref
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

            # 3) Odošli práve jeden príkaz S,<hodnota>, ak treba
            if next_ref is not None:
                ser.write(f"S,{next_ref}\n".encode())

            # 4) Krátka pauza, aby CPU nedrebe 100 %
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
        print("[start_worker] Vlákno už beží — neštartujem znova.")
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
            print("[stop_worker] Pozor: vlákno stále beží po 2 s timeout.")
        worker_thread = None
    _running = None
    print("[stop_worker] Thread closed.")

