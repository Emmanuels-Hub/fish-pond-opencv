import cv2
import logging
import yaml
import sys
import threading
import json
from pathlib import Path
from datetime import datetime
from collections import deque
from flask import Flask, request, jsonify, Response
from ultralytics import YOLO

# Setup logging
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

# Global state
class ProcessingState:
    def __init__(self):
        self.camera_url = None
        self.is_processing = False
        self.model = None
        self.config = None
        self.cap = None
        self.detections_history = deque(maxlen=100)  # Keep last 100 detections
        self.current_frame = None
        self.lock = threading.Lock()
        self.processing_thread = None


state = ProcessingState()


def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    try:
        config_file = Path(config_path)
        if not config_file.exists():
            logger.error(f"Config file not found: {config_path}")
            return None
        
        with open(config_file, "r") as f:
            config = yaml.safe_load(f)
        
        logger.info("Configuration loaded successfully")
        return config
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return None


def load_model(model_path: str):
    """Load YOLO model with error handling."""
    try:
        model_file = Path(model_path)
        if not model_file.exists():
            logger.error(f"Model file not found: {model_path}")
            return None
        
        model = YOLO(model_path)
        logger.info(f"Model loaded successfully from {model_path}")
        return model
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        return None


def initialize_camera(source: str):
    """Initialize camera from URL or local source."""
    try:
        cap = cv2.VideoCapture(source)
        
        if not cap.isOpened():
            logger.error(f"Failed to open camera source: {source}")
            return None
        
        logger.info(f"Camera initialized: {source}")
        return cap
    except Exception as e:
        logger.error(f"Failed to initialize camera: {e}")
        return None


def is_target_class(class_id: int, class_names: dict, target_classes: list) -> bool:
    """Check if detected class is in target classes."""
    try:
        return class_names[class_id] in target_classes
    except (KeyError, IndexError) as e:
        logger.warning(f"Invalid class ID: {class_id}, Error: {e}")
        return False


def process_feed():
    """Main processing loop for camera feed."""
    if not state.model or not state.config or not state.cap:
        logger.error("Model, config, or camera not initialized")
        return
    
    target_classes = state.config["detection"]["target_classes"]
    min_confidence = state.config["detection"]["min_confidence"]
    alert_display = state.config["alert"]["display_alert"]
    alert_color = tuple(state.config["alert"]["alert_color"])
    box_color = tuple(state.config["alert"]["box_color"])
    
    class_names = state.model.names
    frame_count = 0
    
    try:
        while state.is_processing:
            ret, frame = state.cap.read()
            if not ret:
                logger.warning("Failed to read frame from camera")
                break
            
            frame_count += 1
            
            # Run inference
            results = state.model(frame, conf=min_confidence, verbose=False)
            
            detections = []
            for result in results:
                if result.boxes is not None:
                    for box in result.boxes:
                        class_id = int(box.cls)
                        confidence = float(box.conf)
                        
                        if is_target_class(class_id, class_names, target_classes):
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            class_name = class_names[class_id]
                            
                            detections.append({
                                "class": class_name,
                                "confidence": round(confidence, 3),
                                "bbox": [x1, y1, x2, y2],
                                "timestamp": datetime.now().isoformat()
                            })
                            
                            # Draw box on frame
                            cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
                            
                            # Add label
                            label = f"{class_name} {confidence:.2f}"
                            cv2.putText(frame, label, (x1, y1 - 10),
                                      cv2.FONT_HERSHEY_SIMPLEX, 0.5, box_color, 2)
                            
                            if alert_display:
                                # Add alert banner
                                cv2.rectangle(frame, (0, 0), (frame.shape[1], 50), alert_color, -1)
                                cv2.putText(frame, f"ALERT: {class_name} detected!",
                                          (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            
            # Store detection data
            with state.lock:
                if detections:
                    state.detections_history.append({
                        "frame": frame_count,
                        "detections": detections
                    })
                state.current_frame = cv2.imencode('.jpg', frame)[1].tobytes()
            
            logger.debug(f"Frame {frame_count} processed. Detections: {len(detections)}")
    
    except Exception as e:
        logger.error(f"Error in processing loop: {e}")
    finally:
        state.is_processing = False
        if state.cap:
            state.cap.release()
        logger.info("Processing loop ended")


@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "processing": state.is_processing,
        "camera_url": state.camera_url
    })


@app.route('/api/start', methods=['POST'])
def start_processing():
    """Start processing a camera feed."""
    try:
        data = request.get_json()
        camera_url = data.get('camera_url')
        
        if not camera_url:
            return jsonify({"error": "camera_url is required"}), 400
        
        if state.is_processing:
            return jsonify({"error": "Already processing a feed"}), 409
        
        # Load config and model if not already loaded
        if not state.config:
            state.config = load_config()
            if not state.config:
                return jsonify({"error": "Failed to load config"}), 500
        
        if not state.model:
            model_path = state.config["model"]["weights"]
            state.model = load_model(model_path)
            if not state.model:
                return jsonify({"error": "Failed to load model"}), 500
        
        # Initialize camera
        state.cap = initialize_camera(camera_url)
        if not state.cap:
            return jsonify({"error": f"Failed to initialize camera: {camera_url}"}), 400
        
        state.camera_url = camera_url
        state.is_processing = True
        state.detections_history.clear()
        
        # Start processing thread
        state.processing_thread = threading.Thread(target=process_feed, daemon=True)
        state.processing_thread.start()
        
        logger.info(f"Started processing feed: {camera_url}")
        return jsonify({
            "status": "started",
            "camera_url": camera_url,
            "message": "Processing feed..."
        }), 200
    
    except Exception as e:
        logger.error(f"Error starting processing: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/stop', methods=['POST'])
def stop_processing():
    """Stop processing the current feed."""
    try:
        if not state.is_processing:
            return jsonify({"status": "not_processing"}), 200
        
        state.is_processing = False
        
        if state.processing_thread:
            state.processing_thread.join(timeout=5)
        
        if state.cap:
            state.cap.release()
            state.cap = None
        
        logger.info("Stopped processing feed")
        return jsonify({"status": "stopped"}), 200
    
    except Exception as e:
        logger.error(f"Error stopping processing: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/detections', methods=['GET'])
def get_detections():
    """Get recent detections."""
    try:
        with state.lock:
            detections = list(state.detections_history)
        
        return jsonify({
            "total_detections": len(detections),
            "detections": detections
        }), 200
    
    except Exception as e:
        logger.error(f"Error retrieving detections: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/detections/latest', methods=['GET'])
def get_latest_detection():
    """Get the latest detection."""
    try:
        with state.lock:
            if not state.detections_history:
                return jsonify({"detection": None}), 200
            
            latest = list(state.detections_history)[-1]
        
        return jsonify({"detection": latest}), 200
    
    except Exception as e:
        logger.error(f"Error retrieving latest detection: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/stream', methods=['GET'])
def stream_video():
    """Stream video with detections as MJPEG."""
    def generate():
        while state.is_processing:
            with state.lock:
                if state.current_frame:
                    frame = state.current_frame
                else:
                    continue
            
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n'
                   b'Content-Length: ' + str(len(frame)).encode() + b'\r\n\r\n' +
                   frame + b'\r\n')
    
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/api/status', methods=['GET'])
def get_status():
    """Get current processing status."""
    try:
        with state.lock:
            detection_count = len(state.detections_history)
        
        return jsonify({
            "processing": state.is_processing,
            "camera_url": state.camera_url,
            "total_detections": detection_count,
            "model_loaded": state.model is not None,
            "timestamp": datetime.now().isoformat()
        }), 200
    
    except Exception as e:
        logger.error(f"Error retrieving status: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current configuration."""
    try:
        if not state.config:
            return jsonify({"error": "Config not loaded"}), 500
        
        return jsonify(state.config), 200
    
    except Exception as e:
        logger.error(f"Error retrieving config: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/clear-detections', methods=['POST'])
def clear_detections():
    """Clear detection history."""
    try:
        with state.lock:
            state.detections_history.clear()
        
        return jsonify({"status": "cleared"}), 200
    
    except Exception as e:
        logger.error(f"Error clearing detections: {e}")
        return jsonify({"error": str(e)}), 500


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({"error": "Endpoint not found"}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.error(f"Internal server error: {error}")
    return jsonify({"error": "Internal server error"}), 500


if __name__ == '__main__':
    logger.info("Starting Flask server...")
    app.run(host='0.0.0.0', port=8000, debug=False, threaded=True)
