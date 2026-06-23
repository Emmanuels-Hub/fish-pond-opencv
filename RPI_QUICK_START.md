# Raspberry Pi Zero - Quick Start Guide

## What You Get

Two versions of the Raspberry Pi client:

1. **`raspberry_pi_client.py`** - Full-featured version with:
   - Live RTSP streaming
   - Real-time predator detection
   - Buzzer + LED alarms
   - Detailed logging
   - Hardware diagnostics

2. **`raspberry_pi_simple.py`** - Lightweight version for Pi Zero v1.3:
   - Minimal dependencies
   - Just polls server for detections
   - Triggers buzzer on alerts
   - ~10MB RAM usage

## 60-Second Setup

### Step 1: Flash Raspberry Pi OS

1. Download [Raspberry Pi Imager](https://www.raspberrypi.org/software/)
2. Insert MicroSD card
3. Select **Raspberry Pi Zero 2W** (or Zero if using old version)
4. Select **Raspberry Pi OS Lite** (32-bit)
5. Click **WRITE** and wait ~5 minutes

### Step 2: Enable Interfaces

After first boot:

```bash
sudo raspi-config
```

- **Interface Options** → **Camera** → **Enable**
- **Interface Options** → **SSH** → **Enable**
- **Exit** → **Reboot**

### Step 3: Install Basic Dependencies

```bash
sudo apt update
sudo apt install -y python3-pip git

# For buzzer/LED GPIO control
pip3 install gpiozero

# For making HTTP requests
pip3 install requests
```

### Step 4: Install Camera Support

```bash
# For newer Pi OS (Bookworm):
sudo apt install -y libcamera-apps python3-picamera2

# For older Pi OS versions:
sudo apt install -y libraspberrypi-bin libraspberrypi-dev
```

### Step 5: Connect Hardware

**Buzzer** (5V or 3.3V):
- GPIO 17 (Pin 11) → Buzzer +
- GND (Pin 9/14) → Buzzer -

**LED** (Optional):
- GPIO 27 (Pin 13) → LED through 330Ω resistor
- GND → LED -

### Step 6: Clone Code

```bash
git clone <repo-url> /home/pi/pond-monitor
cd /home/pi/pond-monitor

# Or download files manually
```

### Step 7: Test Hardware

```bash
python3 raspberry_pi_simple.py --test
```

**Expected output:**
- 3 buzzer beeps
- "✓ Test complete"

### Step 8: Start Monitoring

```bash
# Replace 192.168.1.100 with your server IP
python3 raspberry_pi_simple.py --server http://192.168.1.100:8000
```

**Expected output:**
```
====================================================
POND SECURITY - Simple Monitor
Server: http://192.168.1.100:8000
Polling every 2 seconds
====================================================
```

## Finding Your Server IP

### If Server is on Another Computer:

```bash
# On the computer running flask_server.py:
ipconfig          # Windows
ifconfig          # Linux/Mac
```

Look for IPv4 address like `192.168.x.x` or `10.0.x.x`

## Using with Flask Server

1. **Start Flask server** on your main computer:

```bash
# Make sure it's listening on 0.0.0.0
python3 flask_server.py
```

2. **Start the Raspberry Pi client**:

```bash
python3 raspberry_pi_simple.py --server http://<YOUR_SERVER_IP>:8000
```

3. **Start streaming** with the full-featured version (for real camera stream):

```bash
python3 raspberry_pi_client.py --server http://<YOUR_SERVER_IP>:8000
```

Then configure the Flask server to use the RTSP stream:

```bash
# Run client_example.py and enter:
# rtsp://raspberrypi.local:8554/stream
```

## Troubleshooting

### Buzzer not working?

```bash
# Test GPIO manually
python3 -c "
from gpiozero import Buzzer
import time
b = Buzzer(17)
b.on()
print('Buzzer ON')
time.sleep(1)
b.off()
print('Buzzer OFF')
"
```

### Server not reachable?

```bash
# Check connectivity
ping 192.168.1.100
curl http://192.168.1.100:8000/api/health
```

### Camera not detected?

```bash
# Check camera connection
vcgencmd get_camera
# Should show: supported=1 detected=1

# List cameras
libcamera-hello --list-cameras
```

## Auto-start on Boot

Create `/home/pi/startup.sh`:

```bash
#!/bin/bash
cd /home/pi/pond-monitor
python3 raspberry_pi_simple.py --server http://192.168.1.100:8000
```

Make executable:
```bash
chmod +x /home/pi/startup.sh
```

Add to crontab:
```bash
crontab -e
# Add this line:
@reboot sleep 5 && /home/pi/startup.sh >> /home/pi/monitor.log 2>&1
```

## Next Steps

### For Full Streaming Setup

See `RPI_SETUP.md` for complete instructions including:
- RTSP server setup
- systemd service installation
- Advanced configuration
- Performance optimization
- Network setup

### Monitor Logs

```bash
# View recent logs
tail -f rpi_monitor_simple.log

# Full logs
cat rpi_monitor_simple.log
```

### Customize

Edit `raspberry_pi_simple.py` to:
- Change GPIO pins: `buzzer_pin=17` parameter
- Adjust alert cooldown: `self.alert_cooldown = 5`
- Add/remove predator classes in `check_detections()`
- Change polling interval: `--interval 5`

## GPIO Pinout Reference

```
Raspberry Pi Zero Pinout (top view):

+5V  ■■ 3.3V
SDA  ■■ SCL
GPIO 4 ■■ GND
GPIO 17 ■■ GPIO 27  ← Buzzer (17), LED (27)
GPIO 22 ■■ GPIO 23
GPIO 24 ■■ GND
GPIO 25 ■■ GPIO 26
CE0  ■■ CE1
MOSI ■■ MISO
SCLK ■■ GND
GPIO 5 ■■ GPIO 6
GPIO 12 ■■ GND
GPIO 13 ■■ GPIO 19
GPIO 16 ■■ GPIO 26
GPIO 20 ■■ GND
GPIO 21 ■■ GPIO 5

Full pinout: https://pinout.xyz/
```

## Predator Classes Monitored

The monitor watches for these YOLO classes by default:
- dog, cat, bird, person, bear, fox, raccoon

Customize in code by editing the `predators` list.

## Power Consumption

- **Raspberry Pi Zero 2W**: ~0.5-1.5W (idle), ~2-3W (active)
- **Buzzer**: ~50mA when active
- **LED**: ~20mA when active

Total: ~5V/2.5A USB power supply recommended

## Tips

1. **Use Pi Zero 2W** - Faster than original Zero, same price
2. **USB power** - Run from USB power bank for portability
3. **Check logs** - Monitor `rpi_monitor_simple.log` for issues
4. **Update regularly** - `sudo apt update && sudo apt upgrade -y`
5. **Disable unused services** - Saves power: `sudo systemctl disable bluetooth`

## What's Next?

- Read `RPI_SETUP.md` for advanced setup
- Read `FLASK_SERVER_USAGE.md` for server details
- Check logs when issues occur
- Monitor server alerts in real-time

Enjoy your Pond Security System! 🐠
