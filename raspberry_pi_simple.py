#!/usr/bin/env python3
"""
Simplified Raspberry Pi Client - Minimal dependencies version
Perfect for Raspberry Pi Zero with low RAM/CPU
"""

import time
import logging
import json
import subprocess
import threading
import signal
import sys
from datetime import datetime
import requests

# Try to import GPIO library, fallback if not available
try:
    from gpiozero import Buzzer, LED
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    print("Warning: gpiozero not installed. GPIO features disabled.")

# Try to import camera, fallback if not available
try:
    from picamera2 import Picamera2
    CAMERA_AVAILABLE = True
except ImportError:
    CAMERA_AVAILABLE = False
    print("Warning: picamera2 not installed. Camera features disabled.")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("rpi_monitor_simple.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class SimplePondMonitor:
    """Lightweight Pond Monitor for Raspberry Pi Zero."""
    
    def __init__(self, server_url="https://fish-pond-eept.onrender.com/", buzzer_pin=17):
        """Initialize monitor."""
        self.server_url = server_url
        self.buzzer_pin = buzzer_pin
        self.is_running = False
        self.buzzer = None
        self.last_alert_time = 0
        self.alert_cooldown = 5
        
        if GPIO_AVAILABLE:
            try:
                self.buzzer = Buzzer(buzzer_pin)
                logger.info(f"✓ Buzzer initialized on GPIO {buzzer_pin}")
            except Exception as e:
                logger.error(f"✗ Buzzer initialization failed: {e}")
        
        logger.info("Monitor ready!")
    
    def test_buzzer(self):
        """Test buzzer."""
        if not self.buzzer:
            logger.warning("Buzzer not available")
            return
        
        logger.info("Testing buzzer (3 beeps)...")
        for _ in range(3):
            self.buzzer.on()
            time.sleep(0.3)
            self.buzzer.off()
            time.sleep(0.2)
        logger.info("✓ Test complete")
    
    def alarm(self, message="ALERT!"):
        """Trigger alarm."""
        if not self.buzzer:
            logger.warning(f"🔔 {message}")
            return
        
        current_time = time.time()
        if current_time - self.last_alert_time < self.alert_cooldown:
            return
        
        self.last_alert_time = current_time
        
        logger.warning(f"🚨 {message}")
        
        # Buzzer pattern
        for _ in range(3):
            self.buzzer.on()
            time.sleep(0.3)
            self.buzzer.off()
            time.sleep(0.2)
    
    def check_detections(self):
        """Check for predator detections."""
        try:
            response = requests.get(
                f"{self.server_url}/api/detections/latest",
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("success") and data.get("detection"):
                    detection = data["detection"]
                    detections_list = detection.get("detections", [])
                    
                    # Predator classes to watch for
                    predators = ["dog", "cat", "bird", "person", "bear", "fox", "raccoon"]
                    
                    for det in detections_list:
                        class_name = det.get("class", "").lower()
                        confidence = det.get("confidence", 0)
                        
                        # Alert if predator with high confidence
                        if any(p in class_name for p in predators) and confidence > 0.5:
                            self.alarm(f"PREDATOR: {class_name} ({confidence:.0%})")
                    
                    return len(detections_list)
            
        except requests.exceptions.RequestException as e:
            logger.debug(f"Server unreachable: {e}")
        except Exception as e:
            logger.error(f"Error: {e}")
        
        return 0
    
    def run(self, check_interval=2):
        """Run monitoring loop."""
        try:
            logger.info("=" * 60)
            logger.info("POND SECURITY - Simple Monitor")
            logger.info(f"Server: {self.server_url}")
            logger.info(f"Polling every {check_interval} seconds")
            logger.info("=" * 60)
            
            self.is_running = True
            
            while self.is_running:
                self.check_detections()
                time.sleep(check_interval)
        
        except KeyboardInterrupt:
            logger.info("\nShutdown...")
        except Exception as e:
            logger.error(f"Error: {e}")
        finally:
            self.stop()
    
    def stop(self):
        """Stop monitoring."""
        self.is_running = False
        if self.buzzer:
            self.buzzer.off()
        logger.info("Monitor stopped")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Simple Pond Monitor")
    parser.add_argument("--server", default="https://fish-pond-eept.onrender.com/", help="Server URL")
    parser.add_argument("--buzzer-pin", type=int, default=17, help="Buzzer GPIO pin")
    parser.add_argument("--test", action="store_true", help="Test buzzer only")
    parser.add_argument("--interval", type=int, default=2, help="Check interval in seconds")
    
    args = parser.parse_args()
    
    monitor = SimplePondMonitor(
        server_url=args.server,
        buzzer_pin=args.buzzer_pin
    )
    
    # Graceful shutdown
    def signal_handler(sig, frame):
        monitor.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    if args.test:
        monitor.test_buzzer()
    else:
        monitor.run(check_interval=args.interval)


if __name__ == "__main__":
    main()
