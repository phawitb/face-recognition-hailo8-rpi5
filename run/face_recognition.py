import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import os
import numpy as np
import cv2
import hailo
from hailo_rpi_common import (
    get_caps_from_pad,
    get_numpy_from_buffer,
    app_callback_class,
)
from face_recognition_pipeline import GStreamerDetectionApp
import socket
import json

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

class user_app_callback_class(app_callback_class):
    def __init__(self):
        super().__init__()

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

def app_callback(pad, info, user_data):
    datas = {}
    buffer = info.get_buffer()
  
    if buffer is None:
        return Gst.PadProbeReturn.OK

    user_data.increment()
    user_data.use_frame = True

    format, width, height = get_caps_from_pad(pad)

    frame = None
    if user_data.use_frame and format is not None and width is not None and height is not None:
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

    # print('\ndatas::::::',datas)
    # print('frame::::::',frame.shape)

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

    return Gst.PadProbeReturn.OK

if __name__ == "__main__":
    user_data = user_app_callback_class()
    app = GStreamerDetectionApp(app_callback, user_data)
    app.run()
