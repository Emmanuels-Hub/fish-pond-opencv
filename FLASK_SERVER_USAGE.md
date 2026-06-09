# Flask CV Server - Usage Guide

A production-ready Flask server for collecting camera feeds from your Raspberry Pi and performing real-time computer vision detection using YOLOv8.

## Quick Start

### 1. Start the Server

```bash
cd /Users/mac/PycharmProjects/fish-pond
./venv/bin/python flask_server.py
```

The server will start on:
- **Localhost:** `http://localhost:8000`
- **Network:** `http://10.1.1.96:8000`

### 2. Test Server Health

```bash
curl http://localhost:8000/api/health
```

Expected response:
```json
{
  "status": "healthy",
  "processing": false,
  "camera_url": null
}
```

## API Endpoints

### Start Processing Feed
**POST** `/api/start`

Start processing a camera feed from a URL (RTSP, HTTP, etc.)

**Request:**
```bash
curl -X POST http://localhost:8000/api/start \
  -H "Content-Type: application/json" \
  -d '{"camera_url": "rtsp://raspberrypi.local:8554/stream"}'
```

**Response:**
```json
{
  "status": "started",
  "camera_url": "rtsp://raspberrypi.local:8554/stream",
  "message": "Processing feed..."
}
```

### Stop Processing Feed
**POST** `/api/stop`

Stop the current processing.

```bash
curl -X POST http://localhost:8000/api/stop
```

**Response:**
```json
{
  "status": "stopped"
}
```

### Get Server Status
**GET** `/api/status`

Check current processing status.

```bash
curl http://localhost:8000/api/status
```

**Response:**
```json
{
  "processing": true,
  "camera_url": "rtsp://raspberrypi.local:8554/stream",
  "total_detections": 42,
  "model_loaded": true,
  "timestamp": "2026-06-09T19:45:30.123456"
}
```

### Get All Detections
**GET** `/api/detections`

Retrieve detection history (last 100 detections).

```bash
curl http://localhost:8000/api/detections
```

**Response:**
```json
{
  "total_detections": 2,
  "detections": [
    {
      "frame": 150,
      "detections": [
        {
          "class": "person",
          "confidence": 0.95,
          "bbox": [100, 50, 200, 400],
          "timestamp": "2026-06-09T19:45:15.123456"
        }
      ]
    }
  ]
}
```

### Get Latest Detection
**GET** `/api/detections/latest`

Get the most recent detection.

```bash
curl http://localhost:8000/api/detections/latest
```

**Response:**
```json
{
  "detection": {
    "frame": 150,
    "detections": [
      {
        "class": "person",
        "confidence": 0.95,
        "bbox": [100, 50, 200, 400],
        "timestamp": "2026-06-09T19:45:15.123456"
      }
    ]
  }
}
```

### Stream Video with Detections
**GET** `/api/stream`

Get MJPEG video stream with detection overlays.

```bash
# Open in browser
http://localhost:8000/api/stream

# Or save to file
curl http://localhost:8000/api/stream > stream.mjpeg
```

### Clear Detection History
**POST** `/api/clear-detections`

Clear all detection history.

```bash
curl -X POST http://localhost:8000/api/clear-detections
```

**Response:**
```json
{
  "status": "cleared"
}
```

### Get Configuration
**GET** `/api/config`

View current configuration from `config.yaml`.

```bash
curl http://localhost:8000/api/config
```

### Health Check
**GET** `/api/health`

Quick health check.

```bash
curl http://localhost:8000/api/health
```

## Python Client Example

Use the provided `client_example.py` for interactive testing:

```bash
./venv/bin/python client_example.py
```

This script will:
1. Check server health
2. Start processing (prompts for camera URL)
3. Display status and detections
4. Stop processing

## Camera URL Examples

### Raspberry Pi with PiCamera Streaming Server (picamera2)
```
rtsp://raspberrypi.local:8554/stream
```

### HTTP Stream
```
http://192.168.1.100:8080/video
```

### Local Webcam
```
0
```

## Configuration

Edit `config.yaml` to customize detection:

```yaml
detection:
  target_classes:
    - "person"
    - "cat"
    - "bird"
  min_confidence: 0.4

alert:
  display_alert: true
  alert_color: [0, 0, 255]  # BGR (Red)
  box_color: [0, 0, 255]
```

## Performance Tips

1. **Lower resolution** in config for faster processing:
   ```yaml
   camera:
     frame_width: 320
     frame_height: 240
   ```

2. **Reduce model size** for speed (trades accuracy):
   ```yaml
   model:
     type: "yolov8n"  # nano is fastest
   ```

3. **Increase confidence threshold** to reduce false positives:
   ```yaml
   detection:
     min_confidence: 0.5
   ```

## Logging

Logs are saved to `flask_server.log` and displayed in terminal. Check for errors:

```bash
tail -f flask_server.log
```

## Troubleshooting

### Port 8000 Already in Use
```bash
# Find and kill process on port 8000
lsof -i :8000
kill -9 <PID>
```

### Camera Connection Failed
- Verify Raspberry Pi is on the network
- Test URL directly: `ffplay rtsp://raspberrypi.local:8554/stream`
- Check firewall settings

### Model Not Loading
- Ensure `yolov8n.pt` exists in project directory
- Download if missing: `wget https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.pt`

### High CPU Usage
- Reduce resolution
- Increase confidence threshold
- Use smaller model (yolov8n instead of yolov8l)

## Production Deployment

For production, use a WSGI server like **Gunicorn**:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 flask_server:app
```

Or **uWSGI**:

```bash
pip install uwsgi
uwsgi --http :8000 --wsgi-file flask_server.py --callable app --processes 4 --threads 2
```

## Project Structure

```
fish-pond/
├── main.py                    # Original local detection script
├── flask_server.py           # Flask server (NEW)
├── client_example.py         # Example client (NEW)
├── config.yaml               # Configuration
├── requirements.txt          # Dependencies
├── yolov8n.pt               # YOLOv8 model weights
├── flask_server.log         # Server logs
└── README.md                # Original documentation
```

## Next Steps

1. ✅ Start the Flask server
2. ✅ Test with health check
3. ✅ Provide Raspberry Pi camera URL
4. ✅ Monitor detections via `/api/detections`
5. ✅ Stream video with `/api/stream`
6. ✅ Integrate with web dashboard (optional)
