#!/usr/bin/env python3
"""
Raspberry Pi Zero W — Fish Pond Security Client
================================================
Hardware:
  - Raspberry Pi Camera Module (via picamera2)
  - PIR sensor          → GPIO 4  (BCM, configurable)
  - 3V Active Buzzer    → GPIO 17 (BCM, configurable)
  - Status LED          → GPIO 27 (BCM, configurable) [optional]

Behaviour:
  1. Waits for PIR motion trigger.
  2. On motion → starts capturing frames from picamera2 and POSTing
     them to the online Flask server every 1/FPS seconds.
  3. Server runs YOLOv8 inference and returns detections.
  4. Pi polls /api/buzzer_alert every 2 s; if a predator is detected
     the 3V buzzer fires a 3-beep pattern.
  5. If PIR goes low for IDLE_TIMEOUT seconds → streaming stops.
  6. Repeat from step 1.
"""

import time
import logging
import threading
import signal
import sys
from pathlib import Path

import cv2
import numpy as np
import requests
from gpiozero import MotionSensor, Buzzer, LED
from picamera2 import Picamera2

# ──────────────────────────── Logging ────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("rpi_client.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# ──────────────────────────── Monitor class ───────────────────────
class PondMonitor:
    """
    Orchestrates PIR-gated video streaming to the online server
    and triggers the buzzer on predator detections.
    """

    def __init__(
        self,
        server_url: str = "http://localhost:8000",
        pir_pin: int = 4,
        buzzer_pin: int = 17,
        led_pin: int = 27,
        camera_resolution: tuple = (640, 480),
        fps: int = 5,
        idle_timeout: int = 30,
        buzzer_cooldown: int = 5,
        buzzer_count: int = 3,
        buzzer_type: str = "active",   # "active" or "passive"
    ):
        self.server_url = server_url.rstrip("/")
        self.pir_pin = pir_pin
        self.buzzer_pin = buzzer_pin
        self.led_pin = led_pin
        self.camera_resolution = camera_resolution
        self.fps = fps
        self.frame_interval = 1.0 / fps
        self.idle_timeout = idle_timeout
        self.buzzer_cooldown = buzzer_cooldown
        self.buzzer_count = buzzer_count
        self.buzzer_type = buzzer_type

        # State flags
        self._running = False
        self._streaming = False
        self._last_motion_time = 0.0
        self._last_buzzer_time = 0.0

        # Threading
        self._stream_thread: threading.Thread | None = None
        self._poll_thread: threading.Thread | None = None
        self._lock = threading.Lock()

        # Hardware handles
        self.pir = None
        self.buzzer = None
        self.led = None
        self.cam = None

        self._init_hardware()

    # ─────────────── Hardware ──────────────────────────────────────

    def _init_hardware(self):
        """Initialise GPIO and camera."""
        logger.info("Initialising hardware …")

        try:
            self.pir = MotionSensor(self.pir_pin, pull_up=False, threshold=0.5,
                                    queue_len=1)
            logger.info(f"  ✓ PIR sensor on GPIO {self.pir_pin}")
        except Exception as e:
            logger.error(f"  ✗ PIR init failed: {e}")
            raise

        try:
            self.buzzer = Buzzer(self.buzzer_pin, active_high=True)
            self.buzzer.off()
            logger.info(f"  ✓ Buzzer on GPIO {self.buzzer_pin} ({self.buzzer_type})")
        except Exception as e:
            logger.error(f"  ✗ Buzzer init failed: {e}")
            raise

        try:
            self.led = LED(self.led_pin)
            self.led.off()
            logger.info(f"  ✓ Status LED on GPIO {self.led_pin}")
        except Exception as e:
            logger.warning(f"  ⚠ LED init failed (non-critical): {e}")
            self.led = None

        try:
            self.cam = Picamera2()
            video_cfg = self.cam.create_video_configuration(
                main={"size": self.camera_resolution, "format": "RGB888"}
            )
            self.cam.configure(video_cfg)
            logger.info(f"  ✓ Camera configured at {self.camera_resolution}")
        except Exception as e:
            logger.error(f"  ✗ Camera init failed: {e}")
            raise

        logger.info("Hardware initialised successfully.")

    def _led(self, state: bool):
        if self.led:
            if state:
                self.led.on()
            else:
                self.led.off()

    # ─────────────── Buzzer alert ──────────────────────────────────

    def _trigger_buzzer(self, class_name: str, confidence: float):
        """Fire the 3-beep predator alert pattern."""
        now = time.time()
        if now - self._last_buzzer_time < self.buzzer_cooldown:
            return
        self._last_buzzer_time = now

        logger.warning(
            f"🚨 PREDATOR ALERT: {class_name}  confidence={confidence:.0%}"
        )

        def _beep():
            for i in range(self.buzzer_count):
                self.buzzer.on()
                time.sleep(0.3)
                self.buzzer.off()
                if i < self.buzzer_count - 1:
                    time.sleep(0.2)
            # Flash LED in sync
            if self.led:
                for _ in range(self.buzzer_count):
                    self._led(True)
                    time.sleep(0.15)
                    self._led(False)
                    time.sleep(0.15)

        threading.Thread(target=_beep, daemon=True).start()

    # ─────────────── Frame capture & push ─────────────────────────

    def _capture_jpeg(self) -> bytes | None:
        """Capture a single frame from picamera2 and encode as JPEG."""
        try:
            arr = self.cam.capture_array()        # RGB888 numpy array
            bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
            _, buf = cv2.imencode(
                ".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 75]
            )
            return buf.tobytes()
        except Exception as e:
            logger.error(f"Frame capture error: {e}")
            return None

    def _push_frame(self, jpeg_bytes: bytes) -> dict | None:
        """POST a JPEG frame to the server."""
        try:
            resp = requests.post(
                f"{self.server_url}/api/frame",
                files={"frame": ("frame.jpg", jpeg_bytes, "image/jpeg")},
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json()
            logger.warning(f"Server returned {resp.status_code}: {resp.text[:120]}")
        except requests.exceptions.Timeout:
            logger.warning("Frame push timed out — skipping frame.")
        except requests.exceptions.ConnectionError:
            logger.warning("Cannot reach server — retrying on next frame.")
        except Exception as e:
            logger.error(f"Unexpected push error: {e}")
        return None

    # ─────────────── Streaming loop ────────────────────────────────

    def _stream_loop(self):
        """Capture and push frames while streaming is active."""
        logger.info(f"▶ Streaming started ({self.fps} fps → {self.server_url})")
        self.cam.start()
        time.sleep(0.8)   # Camera warm-up: first frames can be dark/blank
        self._led(True)

        try:
            while self._streaming:
                t0 = time.time()

                jpeg = self._capture_jpeg()
                if jpeg:
                    result = self._push_frame(jpeg)
                    if result:
                        n = result.get("detections", 0)
                        if n:
                            logger.info(f"  Server: {n} detection(s) on frame {result.get('frame')}")

                elapsed = time.time() - t0
                sleep_time = self.frame_interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

        except Exception as e:
            logger.error(f"Streaming loop error: {e}")
        finally:
            self.cam.stop()
            self._led(False)
            logger.info("⏹ Streaming stopped.")

    def _start_streaming(self):
        """Start the camera streaming thread if not already running."""
        with self._lock:
            if self._streaming:
                return
            self._streaming = True
        # Notify server OUTSIDE the lock — HTTP request must not block mutex
        self._notify_pir(True)

        self._stream_thread = threading.Thread(
            target=self._stream_loop, daemon=True
        )
        self._stream_thread.start()

    def _stop_streaming(self):
        """Signal the streaming thread to stop."""
        with self._lock:
            if not self._streaming:
                return
            self._streaming = False
        # Notify server OUTSIDE the lock — HTTP request must not block mutex
        self._notify_pir(False)

        if self._stream_thread:
            self._stream_thread.join(timeout=10)
        logger.info("Streaming thread joined.")

    def _notify_pir(self, motion: bool):
        """Send PIR state to server (best-effort)."""
        try:
            requests.post(
                f"{self.server_url}/api/pir_event",
                json={"motion": motion},
                timeout=5,
            )
        except Exception:
            pass   # Non-critical

    # ─────────────── Buzzer poll loop ──────────────────────────────

    def _poll_loop(self, interval: float = 2.0):
        """Poll /api/buzzer_alert and trigger buzzer if needed."""
        logger.info("Buzzer poll loop started.")
        while self._running:
            try:
                resp = requests.get(
                    f"{self.server_url}/api/buzzer_alert", timeout=5
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("alert"):
                        # Extract the highest-confidence detection
                        dets = data.get("detections", [])
                        if dets:
                            top = max(dets, key=lambda d: d.get("confidence", 0))
                            self._trigger_buzzer(
                                top.get("class", "Unknown"),
                                top.get("confidence", 0.0),
                            )
            except requests.exceptions.ConnectionError:
                pass   # Server unreachable — keep trying
            except Exception as e:
                logger.error(f"Poll error: {e}")

            time.sleep(interval)

    # ─────────────── PIR loop ──────────────────────────────────────

    def _pir_loop(self):
        """
        Main PIR monitoring loop.

        Starts streaming on motion, stops streaming after IDLE_TIMEOUT
        seconds of no motion.
        """
        logger.info(
            f"PIR loop active. Idle timeout = {self.idle_timeout}s. "
            f"Waiting for motion on GPIO {self.pir_pin} …"
        )

        while self._running:
            if self.pir.motion_detected:
                self._last_motion_time = time.time()

                if not self._streaming:
                    logger.info("🟢 Motion detected — starting stream.")
                    self._start_streaming()
            else:
                # No motion — check idle timeout
                if self._streaming:
                    idle_secs = time.time() - self._last_motion_time
                    if idle_secs >= self.idle_timeout:
                        logger.info(
                            f"🔴 No motion for {idle_secs:.0f}s — stopping stream."
                        )
                        self._stop_streaming()

            time.sleep(0.25)   # Poll PIR 4× per second

    # ─────────────── Public API ────────────────────────────────────

    def test_buzzer(self, count: int = 3):
        """Quick hardware test for the buzzer."""
        logger.info(f"Buzzer test: {count} beep(s) …")
        for i in range(count):
            self.buzzer.on()
            time.sleep(0.3)
            self.buzzer.off()
            if i < count - 1:
                time.sleep(0.2)
        logger.info("Buzzer test complete.")

    def test_camera(self, output: str = "test_capture.jpg"):
        """Capture a single test image."""
        logger.info("Camera test …")
        self.cam.start()
        time.sleep(1)
        jpeg = self._capture_jpeg()
        self.cam.stop()
        if jpeg:
            Path(output).write_bytes(jpeg)
            logger.info(f"Test image saved → {output}")
        else:
            logger.error("Camera test failed.")

    def start(self):
        """Start the full monitoring system."""
        logger.info("=" * 60)
        logger.info("  POND SECURITY — Raspberry Pi Zero Predator Monitor")
        logger.info(f"  Server  : {self.server_url}")
        logger.info(f"  PIR     : GPIO {self.pir_pin}")
        logger.info(f"  Buzzer  : GPIO {self.buzzer_pin}  ({self.buzzer_type})")
        logger.info(f"  Camera  : {self.camera_resolution}  @ {self.fps} fps")
        logger.info(f"  Timeout : {self.idle_timeout}s idle")
        logger.info("=" * 60)

        self._running = True

        # Verify server reachability
        try:
            r = requests.get(f"{self.server_url}/api/health", timeout=8)
            logger.info(f"Server health: {r.json().get('status', 'unknown')}")
        except Exception as e:
            logger.warning(f"Cannot reach server at startup: {e}")

        # Start buzzer poll thread
        self._poll_thread = threading.Thread(
            target=self._poll_loop, daemon=True
        )
        self._poll_thread.start()

        # Run PIR loop on this thread (blocking)
        try:
            self._pir_loop()
        except KeyboardInterrupt:
            logger.info("\nKeyboardInterrupt — shutting down …")
        finally:
            self.stop()

    def stop(self):
        """Gracefully shut down all threads and hardware."""
        logger.info("Shutting down …")
        self._running = False
        self._stop_streaming()

        # Hardware cleanup
        if self.buzzer:
            self.buzzer.off()
        self._led(False)

        logger.info("Goodbye.")


# ──────────────────────────── CLI entry point ─────────────────────
def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Raspberry Pi Zero — Fish Pond Predator Monitor"
    )
    parser.add_argument(
        "--server",
        default="http://localhost:8000",
        help="Online Flask server URL  e.g. https://your-app.onrender.com",
    )
    parser.add_argument("--pir-pin",     type=int, default=4,
                        help="BCM GPIO pin for PIR sensor (default: 4)")
    parser.add_argument("--buzzer-pin",  type=int, default=17,
                        help="BCM GPIO pin for 3V buzzer (default: 17)")
    parser.add_argument("--led-pin",     type=int, default=27,
                        help="BCM GPIO pin for status LED (default: 27)")
    parser.add_argument("--resolution",  default="640x480",
                        help="Camera resolution WxH (default: 640x480)")
    parser.add_argument("--fps",         type=int, default=5,
                        help="Frames per second pushed to server (default: 5)")
    parser.add_argument("--idle-timeout", type=int, default=30,
                        help="Seconds of no-motion before stopping stream (default: 30)")
    parser.add_argument("--buzzer-cooldown", type=int, default=5,
                        help="Minimum seconds between buzzer alerts (default: 5)")
    parser.add_argument("--buzzer-type", choices=["active", "passive"],
                        default="active",
                        help="Buzzer type: active (default) or passive")
    parser.add_argument("--test-buzzer", action="store_true",
                        help="Run a buzzer hardware test and exit")
    parser.add_argument("--test-camera", action="store_true",
                        help="Capture one test image and exit")

    args = parser.parse_args()
    width, height = map(int, args.resolution.split("x"))

    monitor = PondMonitor(
        server_url=args.server,
        pir_pin=args.pir_pin,
        buzzer_pin=args.buzzer_pin,
        led_pin=args.led_pin,
        camera_resolution=(width, height),
        fps=args.fps,
        idle_timeout=args.idle_timeout,
        buzzer_cooldown=args.buzzer_cooldown,
        buzzer_type=args.buzzer_type,
    )

    # Graceful signal handling
    def _signal_handler(sig, frame):
        logger.info(f"Signal {sig} received — stopping …")
        monitor.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    if args.test_buzzer:
        monitor.test_buzzer()
    elif args.test_camera:
        monitor.test_camera()
    else:
        monitor.start()


if __name__ == "__main__":
    main()
