#!/bin/bash

set -e  # Ensure the script stops if any command fails

cd /home/pi/Documents/face-recognition-hailo8-rpi5
source setup_env.sh

streamlit run run/app.py --server.headless true --server.port 8509 &

sleep $10
chromium --start-fullscreen http://localhost:8509 &

sleep $10
python run/face_recognition.py --input usbcam &
