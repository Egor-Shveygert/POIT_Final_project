# Photo‑resistor Regulation Project

This project demonstrates a real-time PI regulation system using an Arduino, two LEDs, and a photoresistor (LDR). The system is controlled and monitored via a web interface built with Flask and Socket.IO.

## Features

- Real-time PI control loop on Arduino with anti-windup and slew-rate limiting
- Live telemetry and control via a web interface (Chart.js, canvas-gauges)
- Data logging to SQLite and JSON
- Session management and historical data visualization
- Modular Python backend with Flask and SQLAlchemy

## Directory Structure

```
POIT_Final_project/
│
├── app.py                # Flask app and Socket.IO server
├── config.py             # Configuration (serial port, DB, paths)
├── models.py             # SQLAlchemy models and DB setup
├── serial_worker.py      # Serial communication and data acquisition
├── static/
│   ├── index.html        # Main web interface (single-page app)
│   ├── main.js           # Frontend logic (Chart.js, Socket.IO, etc.)
│   └── main.css          # Custom styles
├── sketch_may03a/
│   └── sketch_may03a.ino # Arduino firmware (PI controller)
├── data/
│   ├── archive.db        # SQLite database (auto-generated)
│   └── logs.json         # JSON log file (auto-generated)
└── README.md             # This file
```

## Requirements

- Python 3.8+
- Flask
- Flask-SocketIO
- SQLAlchemy
- Arduino IDE (for firmware upload)
- Node.js (optional, for frontend development)

## Setup & Usage

1. **Arduino:**
   - Upload `sketch_may03a.ino` to your Arduino board.
   - Connect LEDs to pins 9 and 10, and LDR to A0.

2. **Python Backend:**
   - Install dependencies:
     ```
     pip install flask flask-socketio sqlalchemy
     ```
   - Adjust `config.py` for your serial port if needed.
   - Run the server:
     ```
     python app.py
     ```
   - The web interface will be available at [http://localhost:5000](http://localhost:5000).

3. **Web Interface:**
   - Open your browser and navigate to [http://localhost:5000](http://localhost:5000).
   - Use the tabs to control the system, view the gauge, and analyze graphs.

## Notes

- All static files are served from the `static/` directory.
- Data is logged both to a SQLite database and a JSON file for flexibility.