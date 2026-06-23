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
import subprocess
import threading
import signal
import sys
from pathlib import Path
from datetime import datetime
from collections import deque
import requests
from gpiozero import Buzzer, LED
from picamera2 import Picamera2
import cv2

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
                 server_url="http://localhost:8000",
                 buzzer_pin=17,
                 led_pin=27,
                 camera_resolution=(640, 480),
                 stream_port=8554):
        """
        Initialize the monitor.
        
        Args:
            server_url: Flask server URL
            buzzer_pin: GPIO pin for buzzer
            led_pin: GPIO pin for status LED
            camera_resolution: Camera resolution (width, height)
            stream_port: RTSP stream port
        """
        self.server_url = server_url
        self.buzzer_pin = buzzer_pin
        self.led_pin = led_pin
        self.camera_resolution = camera_resolution
        self.stream_port = stream_port
        
        # Initialize GPIO
        self.buzzer = None
        self.led = None
        self.picam2 = None
        self.rtsp_server_process = None
        
        # State tracking
        self.is_running = False
        self.detection_history = deque(maxlen=50)
        self.last_buzzer_time = 0
        self.buzzer_cooldown = 5  # Seconds between buzzer alerts
        
        # Threads
        self.poll_thread = None
        self.stream_thread = None
        
        self._initialize_hardware()
    
    def _initialize_hardware(self):
        """Initialize GPIO and camera hardware."""
        try:
            logger.info("Initializing hardware...")
            
            # Initialize GPIO
            self.buzzer = Buzzer(self.buzzer_pin)
            self.led = LED(self.led_pin)
            self.led.on()  # Status LED on during init
            
            logger.info(f"✓ Buzzer initialized on GPIO {self.buzzer_pin}")
            logger.info(f"✓ Status LED initialized on GPIO {self.led_pin}")
            
            # Initialize camera
            self.picam2 = Picamera2()
            config = self.picam2.create_preview_configuration(
                main={"size": self.camera_resolution},
                lores={"size": (320, 240), "format": "YUV420"}
            )
            self.picam2.configure(config)
            self.picam2.start()
            
            logger.info(f"✓ Camera initialized at {self.camera_resolution}")
            time.sleep(1)  # Allow camera to warm up
            
            self.led.off()  # Turn off during normal operation
            
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
            array = self.picam2.capture_array()
            cv2.imwrite(output_path, cv2.cvtColor(array, cv2.COLOR_RGB2BGR))
            logger.info(f"✓ Test image saved to {output_path}")
        except Exception as e:
            logger.error(f"✗ Camera test failed: {e}")
    
    def start_rtsp_stream(self):
        """Start RTSP server for camera streaming."""
        try:
            logger.info(f"Starting RTSP stream on port {self.stream_port}...")
            
            # Use libcamera-vid with rtsp-simple-server for Pi Zero
            cmd = [
                "libcamera-vid",
                "--camera", "0",
                "--nopreview",
                "--rotation", "180",  # Adjust if needed
                "--width", str(self.camera_resolution[0]),
                "--height", str(self.camera_resolution[1]),
                "--framerate", "30",
                "--bitrate", "2000k",
                "--flush",
                "--output", f"rtsp://127.0.0.1:{self.stream_port}/stream"
            ]
            
            self.rtsp_server_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            time.sleep(2)  # Allow stream to start
            logger.info(f"✓ RTSP stream started at rtsp://0.0.0.0:{self.stream_port}/stream")
            
        except Exception as e:
            logger.error(f"✗ Failed to start RTSP stream: {e}")
            logger.info("Make sure 'libcamera-vid' is installed: sudo apt install libcamera-apps")
    
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
        """Poll server for latest detection."""
        try:
            response = requests.get(
                f"{self.server_url}/api/detections/latest",
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("success") and data.get("detection"):
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
                        
                        # Trigger alarm if predator detected with high confidence
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
            logger.info("=" * 60)
            
            self.is_running = True
            
            # Start RTSP stream
            self.start_rtsp_stream()
            
            # Start polling thread
            self.poll_thread = threading.Thread(
                target=self.poll_server_continuously,
                daemon=True
            )
            self.poll_thread.start()
            
            logger.info("✓ Monitor started. Ctrl+C to stop.")
            logger.info(f"Server URL: {self.server_url}")
            logger.info(f"RTSP Stream: rtsp://raspberrypi.local:{self.stream_port}/stream")
            
            # Keep running
            while self.is_running:
                time.sleep(1)
        
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
            
            # Stop RTSP stream
            if self.rtsp_server_process:
                self.rtsp_server_process.terminate()
                self.rtsp_server_process.wait(timeout=5)
                logger.info("✓ RTSP stream stopped")
            
            # Stop camera
            if self.picam2:
                self.picam2.stop()
                logger.info("✓ Camera stopped")
            
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
            "detections_count": len(self.detection_history),
            "server_url": self.server_url,
            "camera_resolution": self.camera_resolution,
            "stream_port": self.stream_port
        }


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Raspberry Pi Predator Monitor with Buzzer Alarm"
    )
    parser.add_argument(
        "--server",
        default="http://localhost:8000",
        help="Flask server URL (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--buzzer-pin",
        type=int,
        default=17,
        help="GPIO pin for buzzer (default: 17)"
    )
    parser.add_argument(
        "--led-pin",
        type=int,
        default=27,
        help="GPIO pin for status LED (default: 27)"
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
        camera_resolution=(width, height)
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
