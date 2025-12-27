# plate_detector.py
import cv2
import time
import re
import uuid
from ultralytics import YOLO
from paddleocr import PaddleOCR

# =========================
# MODEL SETUP
# =========================
yolo = YOLO("best_final_negative.pt")
ocr = PaddleOCR(lang="en", use_angle_cls=True, show_log=False)

# =========================
# YOLO PARAMS (OPTIMIZED)
# =========================
YOLO_CONF = 0.05        # Low for distant plates
YOLO_IOU = 0.30
YOLO_IMGSZ = 1600      # Long-distance detection

# =========================
# PLATE VALIDATION
# =========================
PLATE_REGEX = r"^[A-Z]{2}\d{2}[A-Z]{1,2}\d{3,4}$"
INDIAN_STATES = {
    "AN","AP","AR","AS","BR","CG","CH","DD","DL","DN","GA","GJ","HP","HR",
    "JH","JK","KA","KL","LA","LD","MH","ML","MN","MP","MZ","NL","OD","PB",
    "PY","RJ","SK","TN","TR","TS","UK","UP","WB"
}

# =========================
# TRACKING STATE
# =========================
active_detections = {}  # key -> {session_id, last_seen, plate_number}

# =========================
# HELPERS
# =========================
def clean_plate(text: str):
    text = re.sub(r"[^A-Z0-9]", "", text.upper())
    if not re.match(PLATE_REGEX, text):
        return None
    if text[:2] not in INDIAN_STATES:
        return None
    return text


def normalize_frame(frame):
    """Handle IR / grayscale / low-contrast frames"""
    if len(frame.shape) == 2:
        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(2.0, (8, 8)).apply(l)
    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)


def enhance_crop(crop):
    """OCR-safe enhancement"""
    h, w = crop.shape[:2]

    # 🔥 UPSCALE SMALL PLATES (NO SIZE REJECTION)
    if max(h, w) < 180:
        scale = 180 / max(h, w)
        crop = cv2.resize(
            crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
        )

    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(2.5, (8, 8)).apply(l)
    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)


def bbox_key(box):
    """Stable key for tracking"""
    x1, y1, x2, y2 = box
    return f"{x1//10}_{y1//10}_{x2//10}_{y2//10}"


# =========================
# MAIN DETECTION
# =========================
def detect_plates(frame):
    global active_detections

    results = []
    now = time.time()

    frame = normalize_frame(frame)

    try:
        yolo_results = yolo.predict(
            frame,
            imgsz=YOLO_IMGSZ,
            conf=YOLO_CONF,
            iou=YOLO_IOU,
            verbose=False
        )
    except Exception as e:
        print("YOLO error:", e)
        return []

    current_boxes = set()

    for r in yolo_results:
        if r.boxes is None:
            continue

        for b in r.boxes:
            x1, y1, x2, y2 = map(int, b.xyxy[0])

            # ✅ NO WIDTH / HEIGHT FILTER AT ALL
            crop = frame[y1:y2, x1:x2]
            if crop is None or crop.size == 0:
                continue

            key = bbox_key((x1, y1, x2, y2))
            current_boxes.add(key)

            if key not in active_detections:
                active_detections[key] = {
                    "session_id": str(uuid.uuid4()),
                    "last_seen": now,
                    "plate_number": None,
                }
            else:
                active_detections[key]["last_seen"] = now

            # If plate already known → skip OCR
            if active_detections[key]["plate_number"]:
                results.append({
                    "session_id": active_detections[key]["session_id"],
                    "plate_number": active_detections[key]["plate_number"],
                    "bbox": [[x1,y1],[x2,y1],[x2,y2],[x1,y2]],
                    "crop": crop,
                    "timestamp": now,
                })
                continue

            # OCR
            enhanced = enhance_crop(crop)
            rgb = cv2.cvtColor(enhanced, cv2.COLOR_BGR2RGB)

            try:
                ocr_results = ocr.ocr(rgb, cls=True) or []
                text = "".join(
                    item[1][0]
                    for line in ocr_results if line
                    for item in line
                )

                plate = clean_plate(text)

                if plate:
                    active_detections[key]["plate_number"] = plate

                results.append({
                    "session_id": active_detections[key]["session_id"],
                    "plate_number": plate,
                    "bbox": [[x1,y1],[x2,y1],[x2,y2],[x1,y2]],
                    "crop": crop,
                    "timestamp": now,
                })

            except Exception as e:
                print("OCR error:", e)

    # 🧹 Cleanup stale tracks
    active_detections = {
        k: v for k, v in active_detections.items()
        if (now - v["last_seen"]) < 5.0 or k in current_boxes
    }

    return results
