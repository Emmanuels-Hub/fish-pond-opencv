#!/usr/bin/env python3
"""
Example client for the Flask CV Server.
Shows how to interact with the server API.
"""

import requests
import json
import time

BASE_URL = "http://localhost:8000/api"

def start_feed(camera_url):
    """Start processing a camera feed."""
    response = requests.post(f"{BASE_URL}/start", json={"camera_url": camera_url})
    print(f"Start Response: {response.status_code}")
    print(json.dumps(response.json(), indent=2))
    return response.status_code == 200

def stop_feed():
    """Stop processing the current feed."""
    response = requests.post(f"{BASE_URL}/stop")
    print(f"Stop Response: {response.status_code}")
    print(json.dumps(response.json(), indent=2))

def get_status():
    """Get current server status."""
    response = requests.get(f"{BASE_URL}/status")
    print(f"Status Response: {response.status_code}")
    print(json.dumps(response.json(), indent=2))

def get_detections():
    """Get all detections."""
    response = requests.get(f"{BASE_URL}/detections")
    print(f"Detections Response: {response.status_code}")
    print(json.dumps(response.json(), indent=2))

def get_latest_detection():
    """Get latest detection."""
    response = requests.get(f"{BASE_URL}/detections/latest")
    print(f"Latest Detection Response: {response.status_code}")
    print(json.dumps(response.json(), indent=2))

def clear_detections():
    """Clear detection history."""
    response = requests.post(f"{BASE_URL}/clear-detections")
    print(f"Clear Detections Response: {response.status_code}")
    print(json.dumps(response.json(), indent=2))

def get_health():
    """Check server health."""
    response = requests.get(f"{BASE_URL}/health")
    print(f"Health Response: {response.status_code}")
    print(json.dumps(response.json(), indent=2))

def stream_video():
    """Stream video (save to file)."""
    response = requests.get(f"{BASE_URL}/stream", stream=True)
    print(f"Stream Response: {response.status_code}")
    
    if response.status_code == 200:
        with open("stream_output.mjpeg", "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

if __name__ == "__main__":
    print("=" * 60)
    print("POND SECURITY - Flask CV Server Client")
    print("=" * 60)
    
    # Check health
    print("\n1. Checking server health...")
    get_health()
    
    # Start processing (use RTSP URL from Raspberry Pi)
    # Example: "rtsp://raspberrypi.local:8554/stream"
    print("\n2. Starting feed processing...")
    camera_url = input("Enter camera URL (or press Enter for default): ").strip()
    if not camera_url:
        camera_url = "rtsp://raspberrypi.local:8554/stream"  # Default Raspberry Pi stream
    
    if start_feed(camera_url):
        print("\nProcessing started. Waiting for detections...")
        time.sleep(5)
        
        # Check status
        print("\n3. Checking status...")
        get_status()
        
        # Get detections
        print("\n4. Getting detections...")
        get_detections()
        
        # Get latest detection
        print("\n5. Getting latest detection...")
        get_latest_detection()
        
        # Stop processing
        input("\nPress Enter to stop processing...")
        print("\n6. Stopping feed...")
        stop_feed()
    else:
        print("Failed to start feed")
