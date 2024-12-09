import numpy as np
import cv2
import hailo
import os
import gi
import subprocess
import sys
gi.require_version('Gst', '1.0')
gi.require_version('GObject', '2.0')
from gi.repository import Gst, GObject
from hailo_rpi_common import (
    get_caps_from_pad,
    get_numpy_from_buffer,
    app_callback_class,
)
import socket
import json

if len(sys.argv) > 1:  # Check if an argument is passed
    SOURCE = sys.argv[1]  # First argument after the script name
    
else:
    SOURCE = 'file'

# SOURCE = 'rpi' # usbcam, file
NO_VDO = True

host = '127.0.0.1'  
port = 65432         
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#waiting for socket avalabel
while True:
    try:
        s.connect((host, port))
        break
    except:
        pass

# Initialize GStreamer
Gst.init(None)

def crop_to_aspect_ratio(image, aspect_width, aspect_height):
    height, width = image.shape[:2]
    original_area = width * height
    desired_ratio = aspect_width / aspect_height

    if width / height > desired_ratio:
        new_width = int(height * desired_ratio)
        new_height = height
    else:
        new_width = width
        new_height = int(width / desired_ratio)
    
    x_start = (width - new_width) // 2
    y_start = (height - new_height) // 2
    x_end = x_start + new_width
    y_end = y_start + new_height
    
    cropped_image = image[y_start:y_end, x_start:x_end]
    cropped_area = new_width * new_height
    change_ratio = cropped_area / original_area

    return cropped_image, change_ratio

def get_usb_video_devices():
    """
    Get a list of video devices that are connected via USB and have video capture capability.
    """
    video_devices = [f'/dev/{device}' for device in os.listdir('/dev') if device.startswith('video')]
    usb_video_devices = []

    for device in video_devices:
        try:
            # Use udevadm to get detailed information about the device
            udevadm_cmd = ["udevadm", "info", "--query=all", "--name=" + device]
            result = subprocess.run(udevadm_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            output = result.stdout.decode('utf-8')

            # Check if the device is connected via USB and has video capture capabilities
            if "ID_BUS=usb" in output and ":capture:" in output:
                usb_video_devices.append(device)
        except Exception as e:
            print(f"Error checking device {device}: {e}")

    return usb_video_devices

def app_callback(pad, info):
    """
    Callback function to handle buffer data or events.
    """
    datas = {}
    # Extract the buffer from the pad probe info
    buffer = info.get_buffer()
    if not buffer:
        print("No buffer available.")
        return Gst.PadProbeReturn.OK

    # Extract timestamp or metadata from the buffer
    pts = buffer.pts  # Presentation timestamp
    dts = buffer.dts  # Decode timestamp
    duration = buffer.duration

    print(f"Buffer PTS: {pts}, DTS: {dts}, Duration: {duration}")

    format, width, height = get_caps_from_pad(pad)

    frame = None
    if format is not None and width is not None and height is not None:
        frame = get_numpy_from_buffer(buffer, format, width, height)

    roi = hailo.get_roi_from_buffer(buffer)
    detections = roi.get_objects_typed(hailo.HAILO_DETECTION)

    # Parse the detections
    detection_count = 0
    datas['obj_detection'] = []
    datas['face_detected'] = []
    for detection in detections:
        label = detection.get_label()
        bbox = detection.get_bbox()
        confidence = detection.get_confidence()

        datas['obj_detection'].append([label,confidence,[bbox.xmin(),bbox.ymin(),bbox.xmax(),bbox.ymax()]])

        cls = detection.get_objects_typed(hailo.HAILO_CLASSIFICATION)
        if cls:
            for i,c in enumerate(cls):
                if c.get_label():
                    datas['face_detected'].append([c.get_label(),c.get_confidence()])
            color = (0,255,0)
        else:
            datas['face_detected'].append([None,None])
            color = (0,0,255)

        landmarks = detection.get_objects_typed(hailo.HAILO_LANDMARKS)
        points = landmarks[0].get_points()
        image_height, image_width = frame.shape[:2]

        try:
            xmin, ymin = int(bbox.xmin() * image_width), int(bbox.ymin() * image_height)
            xmax, ymax = int(bbox.xmax() * image_width), int(bbox.ymax() * image_height)
            frame = cv2.rectangle(frame, (xmin, ymin), (xmax, ymax), color, 2)
        except:
            pass
      
    if frame.shape == (640,640,3):
        frame = cv2.resize(frame,(600,400))
    frame,_ = crop_to_aspect_ratio(frame, 6, 4)
    frame = cv2.flip(frame,1)
    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

    print('\ndatas::::::',datas)
    print('frame::::::',frame.shape)

    #sent data
    json_data = json.dumps(datas)
    json_bytes = json_data.encode()
    _, encoded_frame = cv2.imencode('.jpg', frame)
    frame_bytes = encoded_frame.tobytes()
    json_size = len(json_bytes)
    s.sendall(json_size.to_bytes(4, byteorder='big'))
    s.sendall(json_bytes)
    frame_size = len(frame_bytes)
    s.sendall(frame_size.to_bytes(4, byteorder='big'))
    s.sendall(frame_bytes)


    # Example: Modify buffer if needed (e.g., metadata insertion)
    # metadata = Gst.Meta.add_meta(buffer)
    # Modify metadata here if required.

    return Gst.PadProbeReturn.OK  # Continue processing the pipeline

# Create the pipeline ------------------------------------------------------------------
if SOURCE == 'file':
    source_element = "filesrc location=/home/pi/Desktop/face-recognition-hailo8-rpi5/resources/face_recognition.mp4 name=src_0 ! decodebin"
elif SOURCE == 'usbcam':
    usbcam_port = get_usb_video_devices()
    source_element = f"v4l2src device={usbcam_port[0]} ! videoconvert n-threads=2 qos=false"
elif SOURCE == 'rpi':
    source_element = "libcamerasrc ! video/x-raw,format=BGR,width=1536,height=864 ! decodebin"

if NO_VDO:
    video_sink = 'fakesink'
else:
    video_sink = 'ximagesink'
pipeline_string = f"""{source_element} ! queue name=hailo_pre_convert_0 leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! videoconvert n-threads=2 qos=false ! queue name=pre_detector_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! tee name=t hailomuxer name=hmux t. ! queue name=detector_bypass_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hmux. t. ! videoscale name=face_videoscale method=0 n-threads=2 add-borders=false qos=false ! video/x-raw, pixel-aspect-ratio=1/1 ! queue name=pre_face_detector_infer_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hailonet hef-path=/home/pi/Desktop/face-recognition-hailo8-rpi5/resources/scrfd_10g.hef scheduling-algorithm=1 vdevice-key=1 ! queue name=detector_post_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hailofilter so-path=/home/pi/Desktop/face-recognition-hailo8-rpi5/resources/libscrfd_post.so name=face_detection_hailofilter qos=false config-path=/home/pi/Desktop/face-recognition-hailo8-rpi5/resources/configs/scrfd.json function_name=scrfd_10g ! queue leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hmux. hmux. ! queue name=pre_tracker_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hailotracker name=hailo_face_tracker class-id=-1 kalman-dist-thr=0.7 iou-thr=0.8 init-iou-thr=0.9 keep-new-frames=2 keep-tracked-frames=6 keep-lost-frames=8 keep-past-metadata=true qos=false ! queue name=hailo_post_tracker_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hailocropper so-path=/home/pi/Desktop/face-recognition-hailo8-rpi5/resources/libvms_croppers.so function-name=face_recognition internal-offset=true name=cropper2 hailoaggregator name=agg2 cropper2. ! queue name=bypess2_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! agg2. cropper2. ! queue name=pre_face_align_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hailofilter so-path=/home/pi/Desktop/face-recognition-hailo8-rpi5/resources/libvms_face_align.so name=face_align_hailofilter use-gst-buffer=true qos=false ! queue name=detector_pos_face_align_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hailonet hef-path=/home/pi/Desktop/face-recognition-hailo8-rpi5/resources/arcface_mobilefacenet_v1.hef scheduling-algorithm=1 vdevice-key=1 ! queue name=recognition_post_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hailofilter function-name=arcface_rgb so-path=/home/pi/Desktop/face-recognition-hailo8-rpi5/resources/libface_recognition_post.so name=face_recognition_hailofilter qos=false ! queue name=recognition_pre_agg_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! agg2. agg2. ! queue name=hailo_pre_gallery_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hailogallery gallery-file-path=/home/pi/Desktop/face-recognition-hailo8-rpi5/resources/gallery/face_recognition_local_gallery_rgba.json load-local-gallery=true similarity-thr=.4 gallery-queue-size=20 class-id=-1 ! queue name=hailo_pre_draw2 leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hailooverlay name=hailo_overlay qos=false show-confidence=false local-gallery=true line-thickness=5 font-thickness=2 landmark-point-radius=8 ! queue name=hailo_post_draw leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! identity name=identity_callback ! queue name=hailo_display_hailooverlay_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! videoconvert n-threads=4 qos=false name=display_videoconvert qos=false ! queue name=hailo_display_q_0 leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! fpsdisplaysink video-sink={video_sink} name=hailo_display sync=false text-overlay=false"""
# pipeline_string = f"""{source_element} ! queue name=hailo_pre_convert_0 leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! videoconvert n-threads=2 qos=false ! queue name=pre_detector_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! tee name=t hailomuxer name=hmux t. ! queue name=detector_bypass_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hmux. t. ! videoscale name=face_videoscale method=0 n-threads=2 add-borders=false qos=false ! video/x-raw, pixel-aspect-ratio=1/1 ! queue name=pre_face_detector_infer_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hailonet hef-path=/home/pi/Desktop/face-recognition-hailo8-rpi5/resources/scrfd_10g.hef scheduling-algorithm=1 vdevice-key=1 ! queue name=detector_post_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hailofilter so-path=/home/pi/Desktop/face-recognition-hailo8-rpi5/resources/libscrfd_post.so name=face_detection_hailofilter qos=false config-path=/home/pi/Desktop/face-recognition-hailo8-rpi5/resources/configs/scrfd.json function_name=scrfd_10g ! queue leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hmux. hmux. ! queue name=pre_tracker_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hailotracker name=hailo_face_tracker class-id=-1 kalman-dist-thr=0.7 iou-thr=0.8 init-iou-thr=0.9 keep-new-frames=2 keep-tracked-frames=6 keep-lost-frames=8 keep-past-metadata=true qos=false ! queue name=hailo_post_tracker_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hailocropper so-path=/home/pi/Desktop/face-recognition-hailo8-rpi5/resources/libvms_croppers.so function-name=face_recognition internal-offset=true name=cropper2 hailoaggregator name=agg2 cropper2. ! queue name=bypess2_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! agg2. cropper2. ! queue name=pre_face_align_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hailofilter so-path=/home/pi/Desktop/face-recognition-hailo8-rpi5/resources/libvms_face_align.so name=face_align_hailofilter use-gst-buffer=true qos=false ! queue name=detector_pos_face_align_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hailonet hef-path=/home/pi/Desktop/face-recognition-hailo8-rpi5/resources/arcface_mobilefacenet_v1.hef scheduling-algorithm=1 vdevice-key=1 ! queue name=recognition_post_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hailofilter function-name=arcface_rgb so-path=/home/pi/Desktop/face-recognition-hailo8-rpi5/resources/libface_recognition_post.so name=face_recognition_hailofilter qos=false ! queue name=recognition_pre_agg_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! agg2. agg2. ! queue name=hailo_pre_gallery_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hailogallery gallery-file-path=/home/pi/Desktop/face-recognition-hailo8-rpi5/resources/gallery/face_recognition_local_gallery_rgba.json load-local-gallery=true similarity-thr=.4 gallery-queue-size=20 class-id=-1 ! queue name=hailo_pre_draw2 leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hailooverlay name=hailo_overlay qos=false show-confidence=false local-gallery=true line-thickness=5 font-thickness=2 landmark-point-radius=8 ! queue name=hailo_post_draw leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! identity name=identity_callback ! queue name=hailo_display_hailooverlay_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! videoconvert n-threads=4 qos=false name=display_videoconvert qos=false ! queue name=hailo_display_q_0 leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! fpsdisplaysink video-sink=ximagesink name=hailo_display sync=false text-overlay=false"""
# pipeline_string = f"""{source_element} ! queue name=hailo_pre_convert_0 leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! videoconvert n-threads=2 qos=false ! queue name=pre_detector_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! tee name=t hailomuxer name=hmux t. ! queue name=detector_bypass_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hmux. t. ! videoscale name=face_videoscale method=0 n-threads=2 add-borders=false qos=false ! video/x-raw, pixel-aspect-ratio=1/1 ! queue name=pre_face_detector_infer_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hailonet hef-path=/home/pi/Desktop/face-recognition-hailo8-rpi5/resources/scrfd_10g.hef scheduling-algorithm=1 vdevice-key=1 ! queue name=detector_post_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hailofilter so-path=/home/pi/Desktop/face-recognition-hailo8-rpi5/resources/libscrfd_post.so name=face_detection_hailofilter qos=false config-path=/home/pi/Desktop/face-recognition-hailo8-rpi5/resources/configs/scrfd.json function_name=scrfd_10g ! queue leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hmux. hmux. ! queue name=pre_tracker_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hailotracker name=hailo_face_tracker class-id=-1 kalman-dist-thr=0.7 iou-thr=0.8 init-iou-thr=0.9 keep-new-frames=2 keep-tracked-frames=6 keep-lost-frames=8 keep-past-metadata=true qos=false ! queue name=hailo_post_tracker_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hailocropper so-path=/home/pi/Desktop/face-recognition-hailo8-rpi5/resources/libvms_croppers.so function-name=face_recognition internal-offset=true name=cropper2 hailoaggregator name=agg2 cropper2. ! queue name=bypess2_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! agg2. cropper2. ! queue name=pre_face_align_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hailofilter so-path=/home/pi/Desktop/face-recognition-hailo8-rpi5/resources/libvms_face_align.so name=face_align_hailofilter use-gst-buffer=true qos=false ! queue name=detector_pos_face_align_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hailonet hef-path=/home/pi/Desktop/face-recognition-hailo8-rpi5/resources/arcface_mobilefacenet_v1.hef scheduling-algorithm=1 vdevice-key=1 ! queue name=recognition_post_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hailofilter function-name=arcface_rgb so-path=/home/pi/Desktop/face-recognition-hailo8-rpi5/resources/libface_recognition_post.so name=face_recognition_hailofilter qos=false ! queue name=recognition_pre_agg_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! agg2. agg2. ! queue name=hailo_pre_gallery_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hailogallery gallery-file-path=/home/pi/Desktop/face-recognition-hailo8-rpi5/resources/gallery/face_recognition_local_gallery_rgba.json load-local-gallery=true similarity-thr=.4 gallery-queue-size=20 class-id=-1 ! queue name=hailo_pre_draw2 leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hailooverlay name=hailo_overlay qos=false show-confidence=false local-gallery=true line-thickness=5 font-thickness=2 landmark-point-radius=8 ! queue name=hailo_post_draw leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! identity name=identity_callback ! queue name=hailo_display_hailooverlay_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! videoconvert n-threads=4 qos=false name=display_videoconvert qos=false ! queue name=hailo_display_q_0 leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! fpsdisplaysink video-sink=fakesink name=hailo_display sync=false text-overlay=false"""
print('pipeline_string',pipeline_string)

pipeline = Gst.parse_launch(pipeline_string)

# Get the 'identity' element to attach the callback
identity_element = pipeline.get_by_name("identity_callback")

if identity_element:
    # Attach the callback to the pad
    identity_pad = identity_element.get_static_pad("src")
    if identity_pad:
        identity_pad.add_probe(Gst.PadProbeType.BUFFER, app_callback)

# Start the pipeline
pipeline.set_state(Gst.State.PLAYING)

# Run a GStreamer main loop to keep the pipeline running
loop = GObject.MainLoop()
try:
    loop.run()
except KeyboardInterrupt:
    print("Stopping pipeline...")
    pipeline.set_state(Gst.State.NULL)
    loop.quit()
