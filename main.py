import cv2
import logging
import yaml
import sys
from pathlib import Path
from ultralytics import YOLO

### Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("pond_security.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


### Configuration and utility functions
def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    try:
        config_file = Path(config_path)
        if not config_file.exists():
            logger.error(f"Config file not found: {config_path}")
            sys.exit(1)
        
        with open(config_file, "r") as f:
            config = yaml.safe_load(f)
        
        logger.info("Configuration loaded successfully")
        return config
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        sys.exit(1)

### Model loading and camera initialization with error handling
def load_model(model_path: str):
    """Load YOLO model with error handling."""
    try:
        model_file = Path(model_path)
        if not model_file.exists():
            logger.error(f"Model file not found: {model_path}")
            sys.exit(1)
        
        model = YOLO(model_path)
        logger.info(f"Model loaded successfully from {model_path}")
        return model
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        sys.exit(1)

### Camera initialization with error handling
def initialize_camera(source: int | str, width: int, height: int):
    """Initialize camera with error handling."""
    try:
        cap = cv2.VideoCapture(source)
        
        if not cap.isOpened():
            logger.error(f"Failed to open camera source: {source}")
            sys.exit(1)
        
        # Set resolution
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        
        logger.info(f"Camera initialized: {source}")
        return cap
    except Exception as e:
        logger.error(f"Failed to initialize camera: {e}")
        sys.exit(1)

### Detection logic
def is_target_class(class_id: int, class_names: dict, target_classes: list) -> bool:
    """Check if detected class is in target classes."""
    try:
        return class_names[class_id] in target_classes
    except (KeyError, IndexError) as e:
        logger.warning(f"Invalid class ID: {class_id}, Error: {e}")
        return False

### Main detection loop with error handling
def run_detection_loop(cap, model, config: dict):
    """Main detection loop."""
    target_classes = config["detection"]["target_classes"]
    min_confidence = config["detection"]["min_confidence"]
    alert_display = config["alert"]["display_alert"]
    alert_color = tuple(config["alert"]["alert_color"])
    box_color = tuple(config["alert"]["box_color"])
    
    class_names = model.names
    frame_count = 0
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                logger.warning("Failed to read frame from camera")
                break
            
            frame_count += 1
            
            try:
                # Run YOLO inference
                results = model(frame, verbose=False)[0]
                
                alert_triggered = False
                detections = []
                
                for box in results.boxes:
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    
                    if conf < min_confidence:
                        continue
                    
                    label = class_names[cls_id]
                    
                    # Filter only target predators
                    if label in target_classes:
                        alert_triggered = True
                        detections.append((label, conf))
                        
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        
                        # Draw bounding box
                        cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
                        cv2.putText(
                            frame,
                            f"{label} {conf:.2f}",
                            (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            box_color,
                            2,
                        )
                
                # Alert system logic
                if alert_triggered:
                    if alert_display:
                        cv2.putText(
                            frame,
                            "⚠ INTRUDER DETECTED",
                            (20, 50),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            1,
                            alert_color,
                            3,
                        )
                    
                    # Log detections
                    detection_info = ", ".join([f"{label} ({conf:.2f})" for label, conf in detections])
                    logger.warning(f"[Frame {frame_count}] ALERT: {detection_info}")
                
                # Show output
                cv2.imshow("Pond Security AI", frame)
                
                # Exit key
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    logger.info("Exit signal received (q pressed)")
                    break
            
            except Exception as e:
                import traceback
                logger.error(f"Error processing frame {frame_count}: {e}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                continue
    
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Error in detection loop: {e}")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        logger.info(f"Camera released. Total frames processed: {frame_count}")

### Main entry point
def main():
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("POND SECURITY AI - Starting")
    logger.info("=" * 60)
    
    # Load configuration
    config = load_config("config.yaml")
    
    # Load model
    model_path = config["model"]["weights"]
    model = load_model(model_path)
    
    # Initialize camera
    camera_source = config["camera"]["source"]
    frame_width = config["camera"]["frame_width"]
    frame_height = config["camera"]["frame_height"]
    cap = initialize_camera(camera_source, frame_width, frame_height)
    
    # Run detection
    logger.info("Starting detection loop... Press 'q' to quit")
    run_detection_loop(cap, model, config)
    
    logger.info("=" * 60)
    logger.info("POND SECURITY AI - Stopped")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()