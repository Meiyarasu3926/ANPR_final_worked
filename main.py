import os
import time
import json
import base64
import threading
import asyncio
from datetime import datetime
from typing import Optional
import re

import cv2
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from camera_manager import camera_manager
from plate_detector import detect_plates
from config import PLATE_COOLDOWN, SESSION_COOLDOWN
from db_manager import (
    is_registered_plate,
    insert_registered_plate_event,
    insert_unregistered_plate_event,
    update_plate_by_session,
    get_recent_registered_events,
    get_recent_unregistered_events,
    delete_plate_by_session,
)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Storage
DATA_DIR = "data"
REG_DIR = os.path.join(DATA_DIR, "registered")
UNREG_DIR = os.path.join(DATA_DIR, "unregistered")
os.makedirs(REG_DIR, exist_ok=True)
os.makedirs(UNREG_DIR, exist_ok=True)

# Plate validation
PLATE_PATTERNS = [
    re.compile(r"^[A-Z]{2}\d{2}[A-Z]{2}\d{4}$"),
    re.compile(r"^[A-Z]{2}\d{2}[A-Z]{1}\d{4}$"),
]

def is_plate_valid(plate: str) -> bool:
    return bool(plate and any(p.match(plate) for p in PLATE_PATTERNS))

# WebSocket manager
class WSManager:
    def __init__(self):
        self._conns = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._conns.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self._conns:
            self._conns.remove(ws)

    async def broadcast(self, message: dict):
        for ws in list(self._conns):
            try:
                await ws.send_text(json.dumps(message))
            except:
                self.disconnect(ws)

ws_manager = WSManager()

# Runtime state
detection_active = False
processed_sessions = set()
session_last_seen = {}
plate_last_seen = {}
plate_last_status = {}

# Manual capture storage
manual_capture_frame = None

def safe_ts(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d_%H-%M-%S")

def save_crop_image(name: str, crop, registered: bool, ts: datetime) -> Optional[str]:
    folder = REG_DIR if registered else UNREG_DIR
    path = os.path.join(folder, f"{name}_{safe_ts(ts)}.jpg")
    try:
        cv2.imwrite(path, crop)
        return path
    except:
        return None

def load_image_base64(path: Optional[str]) -> Optional[str]:
    if not path or not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def handle_detection(det: dict):
    session_id = det["session_id"]
    plate = det["plate_number"]
    crop = det["crop"]
    bbox = det["bbox"]
    now = time.time()

    # Session cooldown
    last_session = session_last_seen.get(session_id)
    if last_session and (now - last_session) < SESSION_COOLDOWN:
        return
    session_last_seen[session_id] = now

    if session_id in processed_sessions:
        return

    valid_plate = plate if plate and is_plate_valid(plate) else None

    # IN/OUT logic
    if valid_plate:
        last_seen = plate_last_seen.get(valid_plate)
        last_status = plate_last_status.get(valid_plate)

        if last_seen is None:
            status = "IN"
        elif (now - last_seen) > PLATE_COOLDOWN:
            status = "OUT" if last_status == "IN" else "IN"
        else:
            return
    else:
        status = "IN"

    # DB insert
    if valid_plate and is_registered_plate(valid_plate):
        inserted = insert_registered_plate_event(valid_plate, status)
        registered = True
    else:
        inserted = insert_unregistered_plate_event(session_id, valid_plate or "READING…", status)
        registered = False

    if not inserted:
        return

    processed_sessions.add(session_id)

    if not valid_plate:
        delete_plate_by_session(session_id)
        return

    # Update state
    plate_last_seen[valid_plate] = now
    plate_last_status[valid_plate] = status
    update_plate_by_session(session_id, valid_plate)

    # Broadcast
    _, db_ts = inserted
    img_path = save_crop_image(valid_plate, crop, registered, db_ts)
    img_b64 = load_image_base64(img_path)

    payload = {
        "plate": valid_plate,
        "image": img_b64,
        "timestamp": db_ts.isoformat(),
        "bbox": bbox,
        "status": status,
        "registered": registered,
        "tab": "registered" if registered else "unregistered",
        "session_id": session_id,
        "owner": "Registered Vehicle" if registered else "Visitor"
    }

    asyncio.run(ws_manager.broadcast({"type": "vehicle_detected", "data": payload, "switch_to_tab": True}))

def detection_loop():
    global detection_active
    while True:
        try:
            if not camera_manager.active or not detection_active:
                time.sleep(0.05)
                continue

            frame = camera_manager.get_detection_frame()
            if frame is None:
                continue

            detections = detect_plates(frame)
            if not detections:
                continue

            for det in detections:
                handle_detection(det)

        except Exception as e:
            print("Detection error:", e)

        time.sleep(0.02)

threading.Thread(target=detection_loop, daemon=True).start()

# Routes
@app.get("/")
async def ui_root():
    return HTMLResponse(open("index.html", "r", encoding="utf-8").read())

@app.post("/camera/start")
async def camera_start(req: Request):
    data = await req.json()
    return {"success": camera_manager.start(data.get("rtsp_url"))}

@app.post("/camera/stop")
async def camera_stop():
    global detection_active
    detection_active = False
    camera_manager.stop()
    return {"success": True}

@app.post("/detection/start")
async def detection_start(req: Request):
    global detection_active
    detection_active = bool((await req.json()).get("enabled", True))
    return {"success": True}

# 🆕 MANUAL CAPTURE ENDPOINT
@app.post("/manual/capture")
async def manual_capture():
    """Capture current frame for manual entry"""
    global manual_capture_frame
    
    frame = camera_manager.get_detection_frame()
    if frame is None:
        return {"success": False, "message": "Camera not active"}
    
    manual_capture_frame = frame.copy()
    
    # Encode frame to base64
    _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    img_b64 = base64.b64encode(buffer).decode("utf-8")
    
    return {
        "success": True,
        "image": img_b64,
        "message": "Frame captured successfully"
    }

# 🆕 MANUAL ENTRY ENDPOINT
@app.post("/manual/submit")
async def manual_submit(req: Request):
    """Submit manual plate entry"""
    global manual_capture_frame
    
    data = await req.json()
    plate = data.get("plate_number", "").strip().upper()
    status = data.get("status", "IN")
    
    if not plate:
        return {"success": False, "message": "Plate number required"}
    
    if not is_plate_valid(plate):
        return {"success": False, "message": "Invalid plate format"}
    
    # Check registration
    registered = is_registered_plate(plate)
    now = datetime.now()
    
    # Insert to DB
    if registered:
        inserted = insert_registered_plate_event(plate, status)
    else:
        session_id = f"manual_{int(time.time())}"
        inserted = insert_unregistered_plate_event(session_id, plate, status)
    
    if not inserted:
        return {"success": False, "message": "Database insert failed"}
    
    # Save image if available
    img_path = None
    img_b64 = None
    if manual_capture_frame is not None:
        img_path = save_crop_image(plate, manual_capture_frame, registered, now)
        img_b64 = load_image_base64(img_path)
    
    # Update state
    plate_last_seen[plate] = time.time()
    plate_last_status[plate] = status
    
    # Broadcast
    _, db_ts = inserted
    payload = {
        "plate": plate,
        "image": img_b64,
        "timestamp": db_ts.isoformat(),
        "bbox": None,
        "status": status,
        "registered": registered,
        "tab": "registered" if registered else "unregistered",
        "session_id": f"manual_{int(time.time())}",
        "owner": "Registered Vehicle" if registered else "Visitor"
    }
    
    asyncio.run(ws_manager.broadcast({"type": "vehicle_detected", "data": payload, "switch_to_tab": True}))
    
    manual_capture_frame = None
    
    return {
        "success": True,
        "message": f"Manual entry added: {plate} ({status})",
        "registered": registered
    }

@app.get("/vehicles")
async def vehicles():
    return {
        "registered_vehicles": [
            {
                "plate": r["vehicle_number"],
                "timestamp": r["date_time"],
                "status": r["type"],
                "registered": True,
                "owner": r.get("owner_name") or "Registered Vehicle",
                "image": None
            }
            for r in get_recent_registered_events(500)
        ],
        "unregistered_vehicles": [
            {
                "plate": u["plate_number"],
                "timestamp": u["detected_at"],
                "status": u["status"],
                "registered": False,
                "owner": "Visitor",
                "image": None,
                "session_id": u["session_id"]
            }
            for u in get_recent_unregistered_events(500)
        ],
        "active_tab": "registered",
    }

@app.get("/status")
async def status():
    return {
        "camera_active": camera_manager.active,
        "detection_active": detection_active,
    }

@app.get("/video_feed")
async def video_feed():
    return StreamingResponse(camera_manager.generate_stream(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)

if __name__ == "__main__":
    import uvicorn
    print("🚀 ANPR Started with Manual Entry")
    uvicorn.run(app, host="0.0.0.0", port=8000)