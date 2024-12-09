# face-recognition-hailo8-rpi5
## step1 : Install PiOS & Hailo
- **Hardware & os**
    - **Rpi5**
    - **Rassberry Pi OS 64 bit**
        - App >> Rassberry Pi Imager >> Rassberry Pi OS 64 bit
          
git clone https://github.com/phawitb/face-recognition-hailo8-rpi5
# edit directory in run_all.sh
cd /path/to/face-recognition-hailo8-rpi5
source setup_env.sh
pip install -r requirements.txt

chmod +x run_all.sh
chmod +x run/save_face.sh


./Desktop/face-recognition-hailo8-rpi5/run/save_face.sh
./Desktop/face-recognition-hailo8-rpi5/run_all.sh
