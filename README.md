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

## step2 : Download source code and run
- **Install Face recognition app**
```
cd Desktop
git clone https://github.com/phawitb/face-recognition-hailo8-rpi5

cd face-recognition-hailo8-rpi5
chmod +x install.sh
./install.sh

# edit path in FaceApp.sh
# edit path in run/save_faces.sh
# edit path in run/server.py
# if use ipcamera edit in run/server.py
```
- **Test Hailo facerecognition**
```
source setup_env.sh
python run/server.py --input usbcam --testmode true  # usbcam, rpi, file, ipcam
```
- **Run App**
```
# edit source in FaceApp.sh
cd ~
./Desktop/face-recognition-hailo8-rpi5/FaceApp.sh

```



