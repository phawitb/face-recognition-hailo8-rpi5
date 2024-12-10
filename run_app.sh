#!/bin/bash

PROJECT_DIR="/home/pi/Desktop/face-recognition-hailo8-rpi5"  # edit path to directory -----------

set -e  # Ensure the script stops if any command fails

# Read parameter ------------------
input_value=""
testmode_value=""
updatefaces_value="false"  # Default value for --updatefaces
while [[ $# -gt 0 ]]; do
  key="$1"
  case $key in
    --input)
      input_value="$2"
      shift # Move to the next argument
      shift # Skip the value
      ;;
    --testmode)
      testmode_value="$2"
      shift # Move to the next argument
      shift # Skip the value
      ;;
    --updatefaces)
      updatefaces_value="true"  # Set value for --updatefaces
      shift # Skip the parameter
      ;;
    *)
      echo "Unknown parameter: $1"
      shift # Move to the next argument
      ;;
  esac
done
if [[ -z "$input_value" ]]; then
  input_value="usbcam"
fi
if [[ -z "$testmode_value" ]]; then
  testmode_value="false"
fi
if [[ -z "$updatefaces_value" ]]; then
  updatefaces_value="false"
fi
echo "Input parameter: $input_value"
echo "Test mode: $testmode_value"
echo "Update faces: $updatefaces_value"

# Update Face Data ------------------
if [[ "$updatefaces_value" == "true" ]]; then
  ./run/save_faces.sh
fi

# Run App ------------------
cd $PROJECT_DIR 
source setup_env.sh

streamlit run run/app.py --server.headless true --server.port 8509 &

sleep $10
chromium --start-fullscreen http://localhost:8509 &

sleep $10
while true; do
    python run/server.py --input "$input_value" --testmode "$testmode_value"    # usbcam, rpi, file -----------------
    sleep 1 
done
