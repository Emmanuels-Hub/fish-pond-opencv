# 🐟 Pond Security — Cloud Deployment & Hardware Setup Guide

Complete guide for deploying the Flask/YOLOv8 server to **Render.com** and
wiring the Raspberry Pi Zero W with a PIR sensor and 3V buzzer.

---

## Table of Contents
1. [System Architecture](#1-system-architecture)
2. [Server — Deploy to Render.com](#2-server--deploy-to-rendercom)
3. [Raspberry Pi Zero — Hardware Wiring](#3-raspberry-pi-zero--hardware-wiring)
4. [Raspberry Pi Zero — Software Setup](#4-raspberry-pi-zero--software-setup)
5. [Running the System](#5-running-the-system)
6. [API Reference](#6-api-reference)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. System Architecture

```
Internet
  │
  │  HTTPS (frames pushed by Pi)
  ▼
┌──────────────────────────────────────┐
│  Render.com Cloud Server             │
│  flask_server.py + yolov8n.pt        │
│                                      │
│  POST /api/frame   ← Pi pushes JPEG  │
│  GET  /api/buzzer_alert ← Pi polls   │
│  GET  /api/stream  → browser MJPEG   │
└──────────────────────────────────────┘
  ▲         │
  │ HTTPS   │ alert JSON
  │         ▼
┌──────────────────────────────────────┐
│  Raspberry Pi Zero W                 │
│                                      │
│  PIR OUT → GPIO 4  (BCM)             │
│  Buzzer  → GPIO 17 (BCM)             │
│  Camera  → CSI ribbon cable          │
│                                      │
│  rpi_client_pir.py                   │
│   ├── PIR loop (4 Hz poll)           │
│   ├── Frame push thread (5 fps)      │
│   └── Buzzer poll thread (0.5 Hz)    │
└──────────────────────────────────────┘
```

**Key design choice:** The Pi **pushes** JPEG frames to the server (HTTP POST).
No RTSP, no port-forwarding, no firewall headaches — works on any internet connection.

---

## 2. Server — Deploy to Render.com

### 2.1 Prerequisites
- A GitHub account with this repository pushed to it.
- A free [Render.com](https://render.com) account.

### 2.2 Push repo to GitHub

```bash
# In the fish-pond-opencv directory:
git init
git add .
git commit -m "Initial commit — pond security with PIR + cloud server"
git remote add origin https://github.com/YOUR_USERNAME/fish-pond-opencv.git
git push -u origin main
```

> ⚠️ `yolov8n.pt` is ~6 MB. If GitHub rejects it, use Git LFS:
> ```bash
> git lfs install
> git lfs track "*.pt"
> git add .gitattributes yolov8n.pt
> git commit -m "Add yolov8n.pt via LFS"
> git push
> ```

### 2.3 Create Render Web Service

1. Log in → **New → Web Service**
2. Connect your GitHub repo (`fish-pond-opencv`)
3. Render auto-detects `render.yaml` — accept the settings.
4. Click **Create Web Service**.
5. Wait ~3–5 minutes for the build (pip install + model load).
6. Copy your public URL:  
   `https://pond-security-server.onrender.com`  
   (shown at the top of the Render dashboard)

### 2.4 Verify deployment

```bash
curl https://pond-security-server.onrender.com/api/health
# Expected: {"status":"healthy","model_loaded":true, ...}
```

### 2.5 Watch the live feed in a browser

Open:
```
https://pond-security-server.onrender.com/api/stream
```
Once the Pi starts pushing frames, you'll see the annotated MJPEG stream.

> **Note:** Render free tier spins down after 15 min of inactivity.  
> Upgrade to **Starter ($7/mo)** for always-on. Alternatively use **Railway** or **Fly.io**.

---

## 3. Raspberry Pi Zero — Hardware Wiring

### 3.1 PIR Sensor (HC-SR501 or similar)

| PIR Pin | Pi Zero Pin | BCM |
|---------|-------------|-----|
| VCC     | Pin 2 (5V)  | —   |
| GND     | Pin 6 (GND) | —   |
| OUT     | Pin 7       | **GPIO 4** |

> Set the HC-SR501 sensitivity potentiometer to ~medium.  
> Set the time-delay potentiometer to minimum (single-shot mode).

### 3.2 3V Active Buzzer

| Buzzer Pin | Pi Zero Pin  | BCM |
|------------|--------------|-----|
| + (long)   | Pin 11       | **GPIO 17** |
| − (short)  | Pin 9 (GND)  | —   |

> Pi Zero GPIO outputs **3.3 V** — perfect for a 3V active buzzer.  
> No resistor or transistor needed for a buzzer drawing < 15 mA.  
> If your buzzer draws more (e.g., 40 mA), add an NPN transistor (2N2222)
> with a 1 kΩ base resistor between GPIO 17 and the buzzer.

### 3.3 Status LED (optional)

| LED       | Pi Zero Pin  | BCM |
|-----------|--------------|-----|
| Anode (+) | Pin 13       | **GPIO 27** |
| Cathode(−)| Pin 14 (GND) | — (via 330Ω resistor) |

### 3.4 Pi Camera Module

Attach via CSI ribbon cable. Ensure the cable is seated properly (blue tab
facing the USB ports).

### 3.5 Pin Map Reference

```
Pi Zero W GPIO Header (top-down view, USB ports at bottom)

 3V3 [ 1] [ 2] 5V       ← PIR VCC → Pin 2
 SDA [ 3] [ 4] 5V
 SCL [ 5] [ 6] GND      ← PIR GND → Pin 6
PIR4 [ 7] [ 8] TXD      ← PIR OUT → Pin 7 (GPIO 4)
 GND [ 9] [10] RXD      ← Buzzer − → Pin 9
BUZ17[11] [12] GPIO18   ← Buzzer + → Pin 11 (GPIO 17)
      ...
 GND [14] [15]          
      ...
LED27[13]               ← LED anode → Pin 13 (GPIO 27)
```

---

## 4. Raspberry Pi Zero — Software Setup

### 4.1 Flash OS
Flash **Raspberry Pi OS Lite (64-bit)** to a microSD using Raspberry Pi Imager.
Enable SSH and set Wi-Fi credentials in the imager settings.

### 4.2 Enable Camera
```bash
sudo raspi-config
# Interface Options → Camera → Enable → Reboot
```

### 4.3 Install dependencies
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv libopencv-dev pigpio

# Create virtual environment
python3 -m venv ~/pond_env
source ~/pond_env/bin/activate

# Clone the repo (or scp the files)
git clone https://github.com/YOUR_USERNAME/fish-pond-opencv.git
cd fish-pond-opencv

# Install Pi requirements
pip install -r requirements_rpi.txt
```

### 4.4 Enable pigpio daemon (for hardware PWM, needed if using passive buzzer)
```bash
sudo systemctl enable pigpiod
sudo systemctl start pigpiod
```

---

## 5. Running the System

### 5.1 Start the client on Pi Zero

```bash
source ~/pond_env/bin/activate
cd ~/fish-pond-opencv

python rpi_client_pir.py \
  --server https://pond-security-server.onrender.com \
  --pir-pin 4 \
  --buzzer-pin 17 \
  --led-pin 27 \
  --fps 5 \
  --idle-timeout 30 \
  --buzzer-cooldown 5 \
  --buzzer-type active
```

### 5.2 Hardware tests (run before going live)

```bash
# Test buzzer (3 beeps)
python rpi_client_pir.py --server https://... --test-buzzer

# Test camera (saves test_capture.jpg)
python rpi_client_pir.py --server https://... --test-camera
```

### 5.3 Auto-start on boot (systemd)

```bash
sudo nano /etc/systemd/system/pond-monitor.service
```

Paste:
```ini
[Unit]
Description=Pond Security Monitor
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/fish-pond-opencv
ExecStart=/home/pi/pond_env/bin/python rpi_client_pir.py \
  --server https://pond-security-server.onrender.com \
  --pir-pin 4 --buzzer-pin 17 --led-pin 27 \
  --fps 5 --idle-timeout 30
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable pond-monitor
sudo systemctl start pond-monitor
sudo journalctl -u pond-monitor -f   # Follow logs
```

---

## 6. API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Server health + model status |
| POST | `/api/frame` | Pi pushes JPEG frame (multipart `frame` field) |
| POST | `/api/pir_event` | Pi reports PIR state `{"motion": true/false}` |
| GET | `/api/buzzer_alert` | Pi polls for predator alert (one-shot, clears after read) |
| GET | `/api/stream` | Browser MJPEG live stream |
| GET | `/api/status` | Frame count, detection count, PIR state |
| GET | `/api/detections` | All recent detections (last 200 frames) |
| GET | `/api/detections/latest` | Most recent detection entry |
| POST | `/api/clear-detections` | Reset detection history |

---

## 7. Troubleshooting

### "Cannot reach server at startup"
- Check the Render URL is correct.
- Render free tier may be spinning up (takes ~30s on first request).
- Ping it first: `curl https://your-app.onrender.com/api/health`

### "PIR init failed"
- Confirm `--pir-pin` matches the BCM pin you wired OUT to.
- Run `pinout` on the Pi to verify physical ↔ BCM mapping.
- Check `sudo systemctl status pigpiod` is running.

### "Buzzer not sounding"
- Test with `--test-buzzer` flag.
- Verify polarity (+ leg to GPIO, − leg to GND).
- If buzzer is passive, add `--buzzer-type passive` (requires pigpiod).

### "Frame push timed out"
- Pi Zero W has limited bandwidth; reduce `--fps` to 3 or 2.
- Check Wi-Fi signal strength: `iwconfig wlan0`.

### "Model not detecting anything"
- Ensure `yolov8n.pt` is in the repo root on Render.
- Adjust `min_confidence` in `config.yaml` (try 0.3).
- Check `target_classes` includes what you want to detect.

### Render free tier cold-start
The free tier sleeps after 15 min. The Pi client retries connections
automatically. To avoid sleeps, ping the server every 14 min:
```bash
# On any always-on machine / cron job:
*/14 * * * * curl -s https://your-app.onrender.com/api/health > /dev/null
```
