#!/bin/bash

# Source environment variables and activate virtual environment
source setup_env.sh

# Install the required Python dependencies
pip install -r requirements.txt 

chmod +x FaceApp.sh
chmod +x run/save_faces.sh

