# Raspberry Pi Zero Setup Guide

## Hardware Requirements

### Raspberry Pi Zero 2 (Recommended)
- **Processor**: ARM Cortex-A53 (faster than Zero v1)
- **RAM**: 512MB
- **Power**: 5V/2.5A USB power supply recommended

### Components
- **Camera**: Raspberry Pi Camera Module 2 or HQ Camera
- **Buzzer**: Active or Passive piezo buzzer (5V or 3.3V)
- **LED** (optional): Status indicator LED with 330Ω resistor
- **MicroSD Card**: At least 32GB with Raspberry Pi OS Lite
- **Network**: WiFi adapter or Ethernet (Pi Zero 2W has built-in WiFi)

### GPIO Wiring

```
Raspberry Pi Pin Layout (BCM numbering):

Buzzer:
  - GPIO 17 (BCM 17, Physical Pin 11) → Buzzer Positive
  - GND (Physical Pin 9 or 14) → Buzzer Negative

Status LED (Optional):
  - GPIO 27 (BCM 27, Physical Pin 13) → LED through 330Ω resistor → LED Cathode
  - GND → LED Cathode

Camera:
  - CSI Camera Ribbon → Camera Port
```

## Installation Steps

### 1. Prepare Raspberry Pi OS

```bash
# Flash Raspberry Pi OS Lite (32-bit or 64-bit) to MicroSD card
# Using Raspberry Pi Imager or dd command

# On first boot, enable SSH and camera
sudo raspi-config

# Enable interfaces:
# - SSH (Interfacing Options > SSH > Enable)
# - Camera (Interfacing Options > Camera > Enable)
# - GPIO (Interfacing Options > GPIO > Enable)

# Reboot
sudo reboot
```

### 2. System Updates

```bash
sudo apt update
sudo apt upgrade -y

# Install required system packages
sudo apt install -y python3-pip python3-venv
sudo apt install -y libatlas-base-dev libjasper-dev libtiff5 libjasper1
sudo apt install -y libharfbuzz0b libwebp6 libtiff5 libjasper1
sudo apt install -y libopenjp2-7 libopenjp2-7-dev
```

### 3. Install Camera Support

```bash
# For Raspberry Pi OS Bookworm (latest):
sudo apt install -y -o APT::Immediate-Configure=false libcamera-apps
sudo apt install -y libcamera0 python3-libcamera

# For older OS versions:
sudo apt install -y libraspberrypi-bin libraspberrypi-dev
```

### 4. Create Virtual Environment

```bash
cd /home/pi
python3 -m venv pond_env
source pond_env/bin/activate

# Upgrade pip
pip install --upgrade pip setuptools wheel
```

### 5. Install Python Dependencies

```bash
# Core dependencies (lightweight)
pip install requests>=2.31.0 PyYAML>=6.0

# GPIO control
pip install gpiozero pigpio

# For picamera2
sudo apt install -y python3-picamera2

# Optional: for advanced image processing
pip install opencv-python-headless
```

### 6. Download Client Code

```bash
# Clone or download the client code
cd /home/pi
git clone <your-repo> fish-pond-monitor
cd fish-pond-monitor

# Or manually copy raspberry_pi_client.py
```

### 7. Setup RTSP Streaming (rtsp-simple-server)

```bash
# Download rtsp-simple-server
cd /tmp
wget https://github.com/bluenviron/mediamtx/releases/download/v1.3.0/mediamtx_v1.3.0_linux_arm.tar.gz
tar -xzf mediamtx_v1.3.0_linux_arm.tar.gz
sudo mv mediamtx /usr/local/bin/
sudo chmod +x /usr/local/bin/mediamtx

# Alternative: Use libcamera-vid directly (script handles this)
# Make sure libcamera-vid is installed (done above)
```

### 8. Test Hardware

```bash
source pond_env/bin/activate
python3 raspberry_pi_client.py --test

# Expected output:
# - Buzzer test: 3 beeps
# - Camera test: test_image.jpg created
```

## Running the Monitor

### Option 1: Direct Execution

```bash
# Activate environment
source pond_env/bin/activate

# Run with default settings
python3 raspberry_pi_client.py --server http://192.168.1.100:8000

# Run with custom GPIO pins
python3 raspberry_pi_client.py \
  --server http://192.168.1.100:8000 \
  --buzzer-pin 17 \
  --led-pin 27 \
  --resolution 640x480
```

### Option 2: Systemd Service (Persistent)

Create `/etc/systemd/system/pond-monitor.service`:

```ini
[Unit]
Description=Pond Security Monitor
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/fish-pond-monitor
ExecStart=/home/pi/pond_env/bin/python3 /home/pi/fish-pond-monitor/raspberry_pi_client.py \
  --server http://192.168.1.100:8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable pond-monitor.service
sudo systemctl start pond-monitor.service

# Check status
sudo systemctl status pond-monitor.service

# View logs
sudo journalctl -u pond-monitor.service -f
```

### Option 3: Cron Autostart (on reboot)

```bash
crontab -e

# Add line:
@reboot sleep 10 && cd /home/pi/fish-pond-monitor && source pond_env/bin/activate && python3 raspberry_pi_client.py --server http://192.168.1.100:8000 >> rpi_monitor.log 2>&1
```

## Troubleshooting

### Camera Not Detected

```bash
# Check camera connection
vcgencmd get_camera

# Should output: supported=1 detected=1

# List available cameras
libcamera-hello --list-cameras
```

### GPIO/Buzzer Issues

```bash
# Test GPIO manually
python3 -c "from gpiozero import Buzzer; b = Buzzer(17); b.on(); print('On'); b.off()"

# Start pigpiod daemon if needed
sudo pigpiod
```

### RTSP Stream Not Working

```bash
# Check libcamera-vid
which libcamera-vid

# Test stream manually
libcamera-vid --camera 0 --nopreview --flush -o rtsp://127.0.0.1:8554/stream

# In another terminal, test connection
ffplay rtsp://raspberrypi.local:8554/stream
```

### Network Connection

```bash
# Check WiFi connection
ip addr

# Check connectivity to server
ping 192.168.1.100  # Replace with server IP

# Test API endpoint
curl http://192.168.1.100:8000/api/health
```

## Configuration

### GPIO Pins

**Default pins (BCM numbering):**
- Buzzer: GPIO 17
- LED: GPIO 27

To use different pins:

```bash
python3 raspberry_pi_client.py --buzzer-pin 18 --led-pin 23
```

### Camera Resolution

Supported resolutions:
- 1280x720 (720p) - Recommended for better detection
- 640x480 (VGA) - Default, lower bandwidth
- 320x240 - Very lightweight
- 1920x1080 (1080p) - High quality but higher bandwidth/CPU

Usage:

```bash
python3 raspberry_pi_client.py --resolution 1280x720
```

### Server URL

Default: `http://localhost:8000`

For remote server:

```bash
python3 raspberry_pi_client.py --server http://192.168.1.100:8000
```

## Performance Optimization

### For Raspberry Pi Zero v1.3 (if using)

These are resource-constrained, so:

1. **Use lighter camera resolution**: `--resolution 320x240`
2. **Use Raspberry Pi OS Lite** (no desktop GUI)
3. **Reduce polling interval**: Modify in code `interval=5` (5 seconds instead of 2)
4. **Disable unnecessary services**: `sudo systemctl disable bluetooth`

```bash
# Example optimized command
python3 raspberry_pi_client.py \
  --server http://192.168.1.100:8000 \
  --resolution 320x240
```

### Bandwidth Optimization

RTSP stream settings in `libcamera-vid`:
- Bitrate: 2000k (can reduce to 1000k for lower bandwidth)
- Framerate: 30fps (can reduce to 15fps for lower CPU usage)

Edit `raspberry_pi_client.py`, adjust in `start_rtsp_stream()`:

```python
"--bitrate", "1000k",    # Reduce bitrate
"--framerate", "15",     # Reduce framerate
```

## Network Setup

### Static IP (Optional)

Edit `/etc/dhcpcd.conf`:

```bash
sudo nano /etc/dhcpcd.conf

# Add:
interface wlan0
static ip_address=192.168.1.50/24
static routers=192.168.1.1
static domain_name_servers=8.8.8.8
```

### mDNS (Access by hostname)

Raspberry Pi Zero should be accessible via:
```
rtsp://raspberrypi.local:8554/stream
```

If that doesn't work, use IP address instead.

## Monitoring & Logs

### View Live Logs

```bash
tail -f rpi_client.log
```

### Logs Include

- Hardware initialization status
- RTSP stream start/stop
- Server polling attempts
- Predator detections and buzzer triggers
- All errors and warnings

## Flask Server Integration

The Raspberry Pi client expects:

1. **Start endpoint**: `POST /api/start` - starts processing with camera URL
2. **Status endpoint**: `GET /api/status` - returns processing status
3. **Latest detection endpoint**: `GET /api/detections/latest` - returns latest detection

Example server startup with Pi stream:

```bash
python3 flask_server.py --camera-url rtsp://raspberrypi.local:8554/stream
```

Or use the client example to start the feed:

```python
import requests
requests.post("http://localhost:8000/api/start", 
              json={"camera_url": "rtsp://raspberrypi.local:8554/stream"})
```

## Advanced Features

### Custom Predator Classes

Edit `raspberry_pi_client.py`, modify `poll_detections()`:

```python
predator_classes = ["dog", "cat", "bird", "person", "bear", "fox", "raccoon", "snake"]
```

### Custom Alarm Patterns

Edit `trigger_alarm()` method to customize buzzer patterns:

```python
# Fast beeps
for i in range(5):
    self.buzzer.on()
    time.sleep(0.1)
    self.buzzer.off()
    time.sleep(0.1)
```

### Alert Confidence Threshold

Adjust detection confidence threshold in `poll_detections()`:

```python
if any(pred in class_name for pred in predator_classes) and confidence > 0.7:  # 70% confidence
```

## Security Considerations

1. **Network Security**:
   - Use VPN or local network only
   - Don't expose server to internet without authentication
   - Use HTTPS for remote connections

2. **SSH Access**:
   - Change default password: `passwd`
   - Disable password auth: SSH keys only
   - Firewall rules to restrict SSH access

3. **Log Files**:
   - Regularly monitor logs for unauthorized access attempts
   - Consider log rotation for long-running systems

## Support & Debugging

### Useful Commands

```bash
# Check Raspberry Pi specs
cat /proc/cpuinfo

# Monitor resource usage
top -b -n 1 | head -15

# Check disk space
df -h

# Check temperature (Pi Zero 2W)
vcgencmd measure_temp

# List USB devices
lsusb

# Check camera bus
i2cdetect -y 1
```

### Getting Help

Check logs:
```bash
cat rpi_client.log
dmesg | tail -20
```

Test network connectivity:
```bash
ping 8.8.8.8
curl http://192.168.1.100:8000/api/health
```
