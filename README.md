# face-recognition-hailo8-rpi5
## step1 : Install PiOS & Hailo
- **Hardware & os**
    - **Rpi5**
    - **Rassberry Pi OS 64 bit**
        - App >> Rassberry Pi Imager >> Rassberry Pi OS 64 bit

```python
sudo apt update
sudo apt full-upgrade

sudo raspi-config
#Select option "6 Advanced Options", then select option "A8 PCIe Speed". Choose "Yes" to enable PCIe Gen 3 mode. Click "Finish" to exit.
sudo reboot
```

- **Install Hailo Software**

```python
sudo apt install hailo-all
sudo reboot
```

- **Verify Installation**

```python
hailortcli fw-control identify
gst-inspect-1.0 hailotools
gst-inspect-1.0 hailo
```
          
git clone https://github.com/phawitb/face-recognition-hailo8-rpi5
# edit directory in run_all.sh
cd /path/to/face-recognition-hailo8-rpi5
source setup_env.sh
pip install -r requirements.txt

chmod +x run_all.sh
chmod +x run/save_face.sh


./Desktop/face-recognition-hailo8-rpi5/run/save_face.sh
./Desktop/face-recognition-hailo8-rpi5/run_all.sh
