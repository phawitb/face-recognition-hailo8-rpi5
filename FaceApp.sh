#!/bin/bash

PROJECT_DIR="/home/pi/Desktop/face-recognition-hailo8-rpi5"  # edit path to directory -----------

cd $PROJECT_DIR 
source setup_env.sh

# start ui
sleep $3
streamlit run run/app.py --server.headless true --server.port 8509 &
sleep $10
chromium --start-fullscreen http://localhost:8509 &

# update faces 
timeout 180 ./run/save_faces.sh --clean

sleep $10
while true; do
    # update faces
    echo "update faces data....."
    ./run/save_faces.sh

    # run for 900 minutes 
    timeout 900 python run/server.py --input usbcam   # usbcam, rpi, file -----------------
    sleep 1 
done
