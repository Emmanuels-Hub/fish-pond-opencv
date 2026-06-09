# 🐠 Pond Security AI - YOLOv8 Real-time Detection

A production-ready real-time computer vision system for detecting intruders (persons, cats, birds) near fish ponds using YOLOv8.

## Features

✅ **Real-time Detection** - Live video feed analysis with YOLOv8  
✅ **Configurable** - Easy to modify via `config.yaml`  
✅ **Error Handling** - Robust exception handling and logging  
✅ **Alert System** - Visual alerts when intruders detected  
✅ **Logging** - Comprehensive logs for debugging and monitoring  
✅ **Production Ready** - Professional code structure and documentation  

## Requirements

- Python 3.8+
- Webcam or IP camera (RTSP stream)
- ~5GB disk space (for model weights)

## Installation

### 1. Clone/Setup the project
```bash
cd /Users/mac/PycharmProjects/fish-pond
```

### 2. Create virtual environment
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Download YOLOv8 model (if not present)
The `yolov8n.pt` file will auto-download on first run, or manually:
```bash
wget https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.pt
```

## Configuration

Edit `config.yaml` to customize:

```yaml
model:
  weights: "yolov8n.pt"           # Model size: n=nano, s=small, m=medium, l=large, x=xlarge
  confidence_threshold: 0.4        # Detection confidence threshold

camera:
  source: 0                         # 0=webcam, or RTSP URL for IP cameras
  frame_width: 640
  frame_height: 480

detection:
  target_classes:
    - "person"
    - "cat"
    - "bird"
  min_confidence: 0.4

logging:
  level: "INFO"                     # DEBUG, INFO, WARNING, ERROR
```

## Usage

### Run detection
```bash
python main.py
```

### Exit
Press `q` to quit gracefully.

### View logs
```bash
tail -f pond_security.log
```

## Project Structure

```
fish-pond/
├── main.py              # Main application with error handling
├── config.yaml          # Configuration settings
├── requirements.txt     # Python dependencies
├── yolov8n.pt          # YOLOv8 model weights
├── pond_security.log   # Application logs (auto-created)
└── README.md           # This file
```

## Troubleshooting

### Error: "Failed to open camera source"
- Check if webcam is properly connected
- Verify no other app is using the camera
- For IP cameras, ensure RTSP URL is correct

### Error: "Model file not found"
- Ensure `yolov8n.pt` is in the project directory
- Or modify `config.yaml` with correct path

### Slow performance
- Try smaller model: `yolov8n.pt` (current) → fastest
- Reduce frame resolution in `config.yaml`
- Ensure good GPU/CPU resources

### No detections
- Lower `confidence_threshold` in `config.yaml`
- Check camera feed is clear and well-lit
- Verify target classes match actual objects

## Model Options

| Model | Speed | Accuracy | Size |
|-------|-------|----------|------|
| YOLOv8n | ⚡⚡⚡ | ⭐⭐ | 6MB |
| YOLOv8s | ⚡⚡ | ⭐⭐⭐ | 22MB |
| YOLOv8m | ⚡ | ⭐⭐⭐⭐ | 49MB |
| YOLOv8l | 🐢 | ⭐⭐⭐⭐⭐ | 83MB |

## COCO Dataset Classes

The model detects 80 COCO classes. Examples:
- **People**: person, police officer
- **Animals**: cat, dog, bird, cow, sheep, bear, zebra
- **Vehicles**: car, truck, bicycle, motorcycle
- And many more...

Current config targets: `person, cat, bird`

## Performance Notes

- **YOLOv8n** (nano): ~30-50 FPS on CPU, ~100+ FPS on GPU
- **Resolution**: 640x480 is optimal for balance
- **CPU**: For 24/7 operation, consider GPU acceleration

## License

This project uses YOLOv8 from [Ultralytics](https://github.com/ultralytics/ultralytics) under AGPL-3.0.

## Next Steps

- Add email/SMS alerts
- Add cloud storage for detections
- Add database logging
- Add multi-camera support
- Add motion-triggered recording
