#!/bin/bash

PROJECT_DIR="/home/pi/Desktop/face-recognition-hailo8-rpi5"  # edit path to directory -----------

set -e  # Ensure the script stops if any command fails

cd $PROJECT_DIR 
source setup_env.sh

streamlit run run/app.py --server.headless true --server.port 8509 &

sleep $10
chromium --start-fullscreen http://localhost:8509 &

sleep $10
python run/server.py usbcam &  # usbcam, rpi, file
# python run/face_recognition.py --input usbcam &
