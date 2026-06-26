#!/usr/bin/env python3
"""
Raspberry Pi Zero Live Stream Client with Buzzer Alarm
- Streams camera feed via RTSP
- Polls server for predator detections
- Triggers buzzer alarm when predator detected
- Logs all activity
"""

import time
import logging
import json
import threading
import signal
import sys
from pathlib import Path
from datetime import datetime
from collections import deque
import requests
from gpiozero import Buzzer, LED, MotionSensor
from picamera2 import Picamera2
import cv2
import numpy as np

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("rpi_client.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

class RPiPredatorMonitor:
    """Raspberry Pi predator detection monitor with live streaming."""
    
    def __init__(self, 
                 server_url="https://test.anywashapp.com.ng/",
                 buzzer_pin=17,
                 led_pin=27,
                 pir_pin=4,
                 camera_resolution=(640, 480),
                 fps=5,
                 idle_timeout=30):
        """
        Initialize the monitor.
        
        Args:
            server_url: Flask server URL
            buzzer_pin: GPIO pin for buzzer
            led_pin: GPIO pin for status LED
            camera_resolution: Camera resolution (width, height)
            stream_port: RTSP stream port
        """
        self.server_url = server_url.rstrip("/")
        self.buzzer_pin = buzzer_pin
        self.led_pin = led_pin
        self.pir_pin = pir_pin
        self.camera_resolution = camera_resolution
        self.fps = fps
        self.frame_interval = 1.0 / fps
        self.idle_timeout = idle_timeout
        
        # Initialize GPIO
        self.buzzer = None
        self.led = None
        self.pir = None
        self.picam2 = None
        
        # State tracking
        self.is_running = False
        self._streaming = False
        self._last_motion_time = 0.0
        self.detection_history = deque(maxlen=50)
        self.last_buzzer_time = 0
        self.buzzer_cooldown = 5  # Seconds between buzzer alerts
        self._lock = threading.Lock()
        
        # Threads
        self.poll_thread = None
        self.stream_thread = None
        
        self._initialize_hardware()
    
    def _initialize_hardware(self):
        """Initialize GPIO and camera hardware."""
        try:
            logger.info("Initializing hardware...")
            
            # PIR sensor (motion trigger)
            self.pir = MotionSensor(self.pir_pin, pull_up=False,
                                    queue_len=1, threshold=0.5)
            logger.info(f"✓ PIR sensor initialized on GPIO {self.pir_pin}")
            
            # Buzzer
            self.buzzer = Buzzer(self.buzzer_pin)
            self.buzzer.off()
            logger.info(f"✓ Buzzer initialized on GPIO {self.buzzer_pin}")
            
            # Status LED
            self.led = LED(self.led_pin)
            self.led.on()  # Status LED on during init
            logger.info(f"✓ Status LED initialized on GPIO {self.led_pin}")
            
            # Camera — video config for reliable capture_array()
            self.picam2 = Picamera2()
            video_cfg = self.picam2.create_video_configuration(
                main={"size": self.camera_resolution, "format": "RGB888"}
            )
            self.picam2.configure(video_cfg)
            logger.info(f"✓ Camera configured at {self.camera_resolution}")
            
            self.led.off()  # Turn off after init
            
        except Exception as e:
            logger.error(f"✗ Hardware initialization failed: {e}")
            raise
    
    def test_buzzer(self, duration=0.5, count=3):
        """Test buzzer with beeps."""
        try:
            logger.info("Testing buzzer...")
            for i in range(count):
                self.buzzer.on()
                time.sleep(duration)
                self.buzzer.off()
                if i < count - 1:
                    time.sleep(0.2)
            logger.info("✓ Buzzer test complete")
        except Exception as e:
            logger.error(f"✗ Buzzer test failed: {e}")
    
    def test_camera(self, output_path="test_image.jpg"):
        """Capture a test image from camera."""
        try:
            logger.info("Capturing test image...")
            self.picam2.start()
            time.sleep(0.8)  # warm-up
            array = self.picam2.capture_array()
            self.picam2.stop()
            cv2.imwrite(output_path, cv2.cvtColor(array, cv2.COLOR_RGB2BGR))
            logger.info(f"✓ Test image saved to {output_path}")
        except Exception as e:
            logger.error(f"✗ Camera test failed: {e}")
    
    def _capture_jpeg(self) -> bytes | None:
        """Capture a single JPEG frame from picamera2."""
        try:
            arr = self.picam2.capture_array()       # RGB888 numpy array
            bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
            _, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 75])
            return buf.tobytes()
        except Exception as e:
            logger.error(f"Frame capture error: {e}")
            return None

    def _push_frame(self, jpeg_bytes: bytes) -> dict | None:
        """POST a JPEG frame to the server's /api/frame endpoint."""
        try:
            resp = requests.post(
                f"{self.server_url}/api/frame",
                files={"frame": ("frame.jpg", jpeg_bytes, "image/jpeg")},
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json()
            logger.warning(f"Server {resp.status_code}: {resp.text[:120]}")
        except requests.exceptions.Timeout:
            logger.warning("Frame push timed out — skipping.")
        except requests.exceptions.ConnectionError:
            logger.warning("Cannot reach server — retrying next frame.")
        except Exception as e:
            logger.error(f"Push error: {e}")
        return None

    def _stream_loop(self):
        """Capture and push frames while _streaming is True."""
        logger.info(f"▶ Streaming at {self.fps} fps → {self.server_url}")
        self.picam2.start()
        time.sleep(0.8)   # Camera warm-up: first frames can be dark/blank
        if self.led:
            self.led.on()
        try:
            while self._streaming:
                t0 = time.time()
                jpeg = self._capture_jpeg()
                if jpeg:
                    result = self._push_frame(jpeg)
                    if result and result.get("detections", 0):
                        logger.info(
                            f"  Server: {result['detections']} detection(s) "
                            f"on frame {result.get('frame')}"
                        )
                elapsed = time.time() - t0
                wait = self.frame_interval - elapsed
                if wait > 0:
                    time.sleep(wait)
        except Exception as e:
            logger.error(f"Streaming loop error: {e}")
        finally:
            self.picam2.stop()
            if self.led:
                self.led.off()
            logger.info("⏹ Streaming stopped.")

    def start_rtsp_stream(self):  # kept for backward compatibility — not used
        """Deprecated: server now uses push-based /api/frame instead of RTSP."""
        logger.warning("start_rtsp_stream() is deprecated. Frames are pushed via HTTP POST.")
    
    def trigger_alarm(self, detection_data):
        """Trigger buzzer alarm for predator detection."""
        try:
            current_time = time.time()
            
            # Respect cooldown period to avoid continuous buzzing
            if current_time - self.last_buzzer_time < self.buzzer_cooldown:
                return
            
            self.last_buzzer_time = current_time
            
            # Get predator info
            class_name = detection_data.get("class", "Unknown")
            confidence = detection_data.get("confidence", 0)
            
            logger.warning(f"🚨 PREDATOR ALERT: {class_name} (confidence: {confidence:.2%})")
            
            # Alarm pattern: 3 beeps for predator
            for i in range(3):
                self.buzzer.on()
                time.sleep(0.3)
                self.buzzer.off()
                time.sleep(0.2)
            
            # Also flash LED
            for _ in range(3):
                self.led.on()
                time.sleep(0.2)
                self.led.off()
                time.sleep(0.2)
            
        except Exception as e:
            logger.error(f"✗ Failed to trigger alarm: {e}")
    
    def poll_detections(self):
        """Poll server for latest detection and trigger buzzer if needed."""
        try:
            response = requests.get(
                f"{self.server_url}/api/detections/latest",
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                # BUG FIX: server returns {"detection": {...}} — no "success" field
                if data.get("detection"):  
                    detection = data["detection"]
                    timestamp = detection.get("timestamp")
                    
                    # Store in history
                    self.detection_history.append({
                        "timestamp": timestamp,
                        "detections": detection.get("detections", [])
                    })
                    
                    # Check for predators
                    predator_classes = ["dog", "cat", "bird", "person", "bear", "fox", "raccoon"]
                    
                    for det in detection.get("detections", []):
                        class_name = det.get("class", "").lower()
                        confidence = det.get("confidence", 0)
                        
                        if any(pred in class_name for pred in predator_classes) and confidence > 0.5:
                            self.trigger_alarm(det)
                    
                    return detection
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to poll server: {e}")
        except Exception as e:
            logger.error(f"Error polling detections: {e}")
        
        return None
    
    def poll_server_continuously(self, interval=2):
        """Continuously poll server for detections."""
        logger.info(f"Started polling server every {interval} seconds...")
        
        while self.is_running:
            try:
                self.poll_detections()
                time.sleep(interval)
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Polling error: {e}")
                time.sleep(interval)
    
    def start(self):
        """Start the monitoring system."""
        try:
            logger.info("=" * 60)
            logger.info("POND SECURITY - Raspberry Pi Predator Monitor")
            logger.info(f"Server  : {self.server_url}")
            logger.info(f"PIR     : GPIO {self.pir_pin}")
            logger.info(f"Buzzer  : GPIO {self.buzzer_pin}")
            logger.info(f"Camera  : {self.camera_resolution} @ {self.fps} fps")
            logger.info("=" * 60)
            
            self.is_running = True
            
            # Start polling thread (buzzer detection)
            self.poll_thread = threading.Thread(
                target=self.poll_server_continuously,
                daemon=True
            )
            self.poll_thread.start()
            
            logger.info("✓ Monitor started. Ctrl+C to stop.")
            logger.info(f"Waiting for PIR motion on GPIO {self.pir_pin} …")
            
            # PIR-gated streaming loop
            while self.is_running:
                if self.pir.motion_detected:
                    self._last_motion_time = time.time()
                    if not self._streaming:
                        logger.info("🟢 Motion detected — starting stream.")
                        self._streaming = True
                        self.stream_thread = threading.Thread(
                            target=self._stream_loop, daemon=True
                        )
                        self.stream_thread.start()
                else:
                    if self._streaming:
                        idle = time.time() - self._last_motion_time
                        if idle >= self.idle_timeout:
                            logger.info(f"🔴 No motion for {idle:.0f}s — stopping stream.")
                            self._streaming = False
                            if self.stream_thread:
                                self.stream_thread.join(timeout=10)
                time.sleep(0.25)
        
        except KeyboardInterrupt:
            logger.info("\nShutdown requested...")
        except Exception as e:
            logger.error(f"✗ Monitor error: {e}")
        finally:
            self.stop()
    
    def stop(self):
        """Stop the monitoring system."""
        try:
            logger.info("Stopping monitor...")
            self.is_running = False
            self._streaming = False  # stop streaming thread
            
            if self.stream_thread:
                self.stream_thread.join(timeout=10)
            
            # Turn off buzzer and LED
            if self.buzzer:
                self.buzzer.off()
            if self.led:
                self.led.off()
                logger.info("✓ GPIO cleaned up")
            
            logger.info("=" * 60)
            logger.info("Monitor stopped")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
    
    def get_status(self):
        """Get current status."""
        return {
            "is_running": self.is_running,
            "streaming": self._streaming,
            "detections_count": len(self.detection_history),
            "server_url": self.server_url,
            "camera_resolution": self.camera_resolution,
        }


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Raspberry Pi Predator Monitor with Buzzer Alarm"
    )
    parser.add_argument(
        "--server",
        default="https://test.anywashapp.com.ng",
        help="Flask server URL"
    )
    parser.add_argument(
        "--buzzer-pin",
        type=int,
        default=17,
        help="BCM GPIO pin for buzzer (default: 17)"
    )
    parser.add_argument(
        "--led-pin",
        type=int,
        default=27,
        help="BCM GPIO pin for status LED (default: 27)"
    )
    parser.add_argument(
        "--pir-pin",
        type=int,
        default=4,
        help="BCM GPIO pin for PIR sensor (default: 4)"
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=5,
        help="Frames per second pushed to server (default: 5)"
    )
    parser.add_argument(
        "--idle-timeout",
        type=int,
        default=30,
        help="Seconds of no-motion before stopping stream (default: 30)"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run hardware tests only"
    )
    parser.add_argument(
        "--resolution",
        default="640x480",
        help="Camera resolution WIDTHxHEIGHT (default: 640x480)"
    )
    
    args = parser.parse_args()
    
    # Parse resolution
    width, height = map(int, args.resolution.split("x"))
    
    # Initialize monitor
    monitor = RPiPredatorMonitor(
        server_url=args.server,
        buzzer_pin=args.buzzer_pin,
        led_pin=args.led_pin,
        pir_pin=args.pir_pin,
        camera_resolution=(width, height),
        fps=args.fps,
        idle_timeout=args.idle_timeout,
    )
    
    # Handle signals
    def signal_handler(sig, frame):
        logger.info("\nReceived signal, shutting down...")
        monitor.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        if args.test:
            logger.info("Running hardware tests...")
            monitor.test_buzzer()
            monitor.test_camera()
            logger.info("Tests complete!")
        else:
            monitor.start()
    
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
