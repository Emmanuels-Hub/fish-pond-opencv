import cv2
import logging
import yaml
import threading
import numpy as np
from pathlib import Path
from datetime import datetime
from collections import deque
from flask import Flask, request, jsonify, Response
from ultralytics import YOLO

# ─────────────────────────── Logging ────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("flask_server.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ─────────────────────────── Global state ───────────────────────
class ProcessingState:
    def __init__(self):
        self.model = None
        self.config = None
        self.detections_history = deque(maxlen=200)   # rolling window
        self.current_frame: bytes | None = None        # latest annotated JPEG
        self.latest_alert: dict | None = None          # for Pi buzzer polling
        self.lock = threading.Lock()
        self.frame_count = 0
        self.pir_active = False                        # set by /api/pir_event

state = ProcessingState()


# ─────────────────────────── Helpers ────────────────────────────
def load_config(config_path: str = "config.yaml") -> dict | None:
    """Load configuration from YAML file."""
    try:
        cfg_file = Path(config_path)
        if not cfg_file.exists():
            logger.warning(f"Config file not found: {config_path}; using defaults.")
            return _default_config()
        with open(cfg_file, "r") as f:
            config = yaml.safe_load(f)
        logger.info("Configuration loaded successfully")
        return config
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return _default_config()


def _default_config() -> dict:
    return {
        "model": {"weights": "yolov8n.pt"},
        "detection": {
            "target_classes": ["person", "cat", "dog", "bird", "bear"],
            "min_confidence": 0.4,
        },
        "alert": {
            "display_alert": True,
            "alert_color": [0, 0, 255],
            "box_color": [0, 255, 0],
        },
    }


def load_model(model_path: str) -> YOLO | None:
    """Load YOLOv8 model."""
    try:
        p = Path(model_path)
        if not p.exists():
            logger.error(f"Model file not found: {model_path}")
            return None
        model = YOLO(str(p))
        logger.info(f"Model loaded: {model_path}")
        return model
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        return None


def is_target_class(class_id: int, class_names: dict, target_classes: list) -> bool:
    try:
        return class_names[class_id] in target_classes
    except (KeyError, IndexError):
        return False


def run_inference(frame_bgr: np.ndarray) -> tuple[np.ndarray, list, bool]:
    """
    Run YOLOv8 inference on a BGR frame.

    Returns:
        annotated_frame  – frame with bounding boxes drawn
        detections       – list of detection dicts
        predator_found   – True if any target class detected
    """
    cfg = state.config
    target_classes = cfg["detection"]["target_classes"]
    min_confidence = cfg["detection"]["min_confidence"]
    alert_display = cfg["alert"]["display_alert"]
    alert_color = tuple(cfg["alert"]["alert_color"])
    box_color = tuple(cfg["alert"]["box_color"])

    results = state.model(frame_bgr, conf=min_confidence, verbose=False)
    class_names = state.model.names

    detections = []
    predator_found = False

    for result in results:
        if result.boxes is None:
            continue
        for box in result.boxes:
            class_id = int(box.cls)
            confidence = float(box.conf)

            if not is_target_class(class_id, class_names, target_classes):
                continue

            x1, y1, x2, y2 = map(int, box.xyxy[0])
            class_name = class_names[class_id]
            predator_found = True

            detections.append({
                "class": class_name,
                "confidence": round(confidence, 3),
                "bbox": [x1, y1, x2, y2],
                "timestamp": datetime.now().isoformat(),
            })

            # Draw bounding box
            cv2.rectangle(frame_bgr, (x1, y1), (x2, y2), box_color, 2)
            label = f"{class_name} {confidence:.2f}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
            cv2.rectangle(frame_bgr, (x1, y1 - th - 8), (x1 + tw + 4, y1), box_color, -1)
            cv2.putText(frame_bgr, label, (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2)

            if alert_display:
                cv2.rectangle(frame_bgr, (0, 0), (frame_bgr.shape[1], 52), alert_color, -1)
                cv2.putText(frame_bgr, f"ALERT: {class_name} detected!",
                            (10, 36), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

    return frame_bgr, detections, predator_found


# ─────────────────────────── Startup ────────────────────────────
def startup():
    """Load config and model at server startup."""
    state.config = load_config()
    model_path = state.config["model"].get("weights", "yolov8n.pt")
    state.model = load_model(model_path)
    if state.model:
        logger.info("🟢 Server ready — waiting for frames from Raspberry Pi.")
    else:
        logger.error("🔴 Model failed to load. POST /api/frame will return 503.")


# Call startup immediately (before first request)
with app.app_context():
    startup()


# ─────────────────────────── Routes ─────────────────────────────

@app.route("/api/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "model_loaded": state.model is not None,
        "frame_count": state.frame_count,
        "pir_active": state.pir_active,
        "timestamp": datetime.now().isoformat(),
    })


@app.route("/api/frame", methods=["POST"])
def receive_frame():
    """
    Receive a JPEG frame pushed by the Raspberry Pi.

    Expects multipart/form-data with field 'frame' (JPEG bytes).
    Runs YOLOv8 inference and stores annotated frame + detections.
    """
    if state.model is None:
        return jsonify({"error": "Model not loaded"}), 503

    if "frame" not in request.files:
        return jsonify({"error": "Missing 'frame' field in multipart form data"}), 400

    try:
        file_bytes = request.files["frame"].read()
        np_arr = np.frombuffer(file_bytes, np.uint8)
        frame_bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if frame_bgr is None:
            return jsonify({"error": "Could not decode image"}), 400

        annotated, detections, predator_found = run_inference(frame_bgr)

        # Encode annotated frame back to JPEG
        _, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
        jpeg_bytes = jpeg.tobytes()

        with state.lock:
            state.frame_count += 1
            state.current_frame = jpeg_bytes

            if detections:
                entry = {
                    "frame": state.frame_count,
                    "detections": detections,
                    "timestamp": datetime.now().isoformat(),
                }
                state.detections_history.append(entry)

                if predator_found:
                    # Keep the latest alert for the Pi to poll
                    state.latest_alert = {
                        "alert": True,
                        "detections": detections,
                        "timestamp": datetime.now().isoformat(),
                    }

        logger.debug(f"Frame {state.frame_count} — {len(detections)} detection(s)")

        return jsonify({
            "frame": state.frame_count,
            "detections": len(detections),
            "predator_found": predator_found,
        }), 200

    except Exception as e:
        logger.error(f"Error processing frame: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/pir_event", methods=["POST"])
def pir_event():
    """
    Receive PIR sensor state updates from the Raspberry Pi.

    JSON body: {"motion": true/false}
    """
    try:
        data = request.get_json(force=True)
        motion = bool(data.get("motion", False))
        with state.lock:
            state.pir_active = motion
        logger.info(f"PIR event: motion={'YES' if motion else 'NO'}")
        return jsonify({"pir_active": state.pir_active}), 200
    except Exception as e:
        logger.error(f"PIR event error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/buzzer_alert", methods=["GET"])
def buzzer_alert():
    """
    Pi polls this endpoint to check if it should trigger the buzzer.

    Returns the latest unacknowledged predator alert, then clears it.
    """
    with state.lock:
        alert = state.latest_alert
        state.latest_alert = None   # Consume the alert (one-shot)

    if alert:
        return jsonify(alert), 200
    return jsonify({"alert": False}), 200


@app.route("/api/stream", methods=["GET"])
def stream_video():
    """Stream the latest annotated frame as MJPEG (for browser monitoring)."""
    def generate():
        while True:
            with state.lock:
                frame = state.current_frame
            if frame:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(frame)).encode() + b"\r\n\r\n" +
                    frame + b"\r\n"
                )
            else:
                # Send a blank grey frame when no feed is active
                import time
                time.sleep(0.2)

    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/detections", methods=["GET"])
def get_detections():
    """Return all recent detections (last 200 frames)."""
    with state.lock:
        detections = list(state.detections_history)
    return jsonify({
        "total_detections": len(detections),
        "detections": detections,
    }), 200


@app.route("/api/detections/latest", methods=["GET"])
def get_latest_detection():
    """Return the most recent detection entry."""
    with state.lock:
        if not state.detections_history:
            return jsonify({"detection": None}), 200
        latest = list(state.detections_history)[-1]
    return jsonify({"detection": latest}), 200


@app.route("/api/status", methods=["GET"])
def get_status():
    """Return server processing status."""
    with state.lock:
        count = len(state.detections_history)
        pir = state.pir_active
        frames = state.frame_count

    return jsonify({
        "model_loaded": state.model is not None,
        "frame_count": frames,
        "total_detections": count,
        "pir_active": pir,
        "timestamp": datetime.now().isoformat(),
    }), 200


@app.route("/api/clear-detections", methods=["POST"])
def clear_detections():
    """Clear detection history."""
    with state.lock:
        state.detections_history.clear()
        state.latest_alert = None
    return jsonify({"status": "cleared"}), 200


@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404


@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({"error": "Internal server error"}), 500


# ─────────────────────────── Entry point ────────────────────────
if __name__ == "__main__":
    logger.info("Starting Flask server on 0.0.0.0:8000 ...")
    app.run(host="0.0.0.0", port=8000, debug=False, threaded=True)
