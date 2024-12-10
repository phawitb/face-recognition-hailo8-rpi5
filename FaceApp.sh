#!/bin/bash

PROJECT_DIR="/home/pi/Desktop/face-recognition-hailo8-rpi5"  # edit path here -----------

cd $PROJECT_DIR 
source setup_env.sh

# start ui
sleep $3
streamlit run run/app.py --server.headless true --server.port 8509 &
sleep $10
chromium --start-fullscreen http://localhost:8509 &

# update faces 
timeout 30 ./run/save_faces.sh --clean

sleep $10
while true; do
    # update faces
    echo "update faces data....."
    timeout 10 ./run/save_faces.sh

    # run for 15 minutes(900sec) 
    timeout 900 python run/server.py --input usbcam   # edit source [usbcam, rpi, file, ipcam] -----------------
    sleep 1 
done
