import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
from hailo_rpi_common import (
    get_caps_from_pad,
    get_numpy_from_buffer,
    app_callback_class,
)
import hailo
import argparse
# import hailo
import socket
import json
import cv2

RESOURES_PATH = 'resources'
INPUT = 'file'

# host = '127.0.0.1'  # Receiver's IP (localhost for testing)
# port = 65432         # Same port as the receiver script
# s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# # with sockyet.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
# while True:
#     try:
#         s.connect((host, port))
#         break
#     except:
#         pass

parser = argparse.ArgumentParser(description="Process input arguments.")
parser.add_argument('--input', type=str, help='Specify the input type (e.g., cam)', required=True)
args = parser.parse_args()
if args.input:
    INPUT = args.input

# Initialize GStreamer
Gst.init(None)

# Define the callback function
def onframe_processed(pad, info, user):
    print(f"Frame processed: Pad: {pad}, Info: {info}, User Data: {user}")

    datas = {}

    # Get the GstBuffer from the probe info
    buffer = info.get_buffer()
    # Check if the buffer is valid
    if buffer is None:
        return Gst.PadProbeReturn.OK

    # Using the user_data to count the number of frames
    # user_data.increment()
    # user_data.use_frame = True

    # Get the caps from the pad
    format, width, height = get_caps_from_pad(pad)

    # If the user_data.use_frame is set to True, we can get the video frame from the buffer
    frame = None
    # if user_data.use_frame and 
    if format is not None and width is not None and height is not None:
        # Get video frame
        frame = get_numpy_from_buffer(buffer, format, width, height)

    # Get the detections from the buffer
    roi = hailo.get_roi_from_buffer(buffer)
    detections = roi.get_objects_typed(hailo.HAILO_DETECTION)
    # ['GLOBAL_ID', 'HAILO_CLASSIFICATION', 'HAILO_CLASS_MASK', 'HAILO_CONF_CLASS_MASK', 'HAILO_DEPTH_MASK', 'HAILO_DETECTION', 'HAILO_LANDMARKS', 'HAILO_MATRIX', 
    # 'HAILO_ROI', 'HAILO_TILE', 'HAILO_UNIQUE_ID', 'HAILO_USER_META', 'HailoBBox', 'HailoClassMask', 'HailoClassification', 'HailoConfClassMask', 'HailoDepthMask', 'HailoDetection', 'HailoLandmarks', 'HailoMainObject', 'HailoMask', 'HailoMatrix', 'HailoObject', 'HailoPoint', 'HailoROI', 'HailoTensor', 'HailoTileROI', 'HailoUniqueID', 'HailoUserMeta', 'MULTI_SCALE', 'SINGLE_SCALE', 'TRACKING_ID', '__doc__', '__file__', '__loader__', '__name__', '__package__', '__spec__', 'access_HailoMainObject_from_desc', 'access_HailoROI_from_desc', 'add_classification', 'add_detection', 'add_detections', 'create_flattened_bbox', 'flatten_hailo_roi', 'get_hailo_detections', 'get_hailo_roi_instances', 'get_hailo_tiles', 'get_roi_from_buffer', 'hailo_object_t', 'hailo_tiling_mode_t', 'hailo_unique_id_mode_t']

    # Parse the detections
    detection_count = 0
    for detection in detections:
        label = detection.get_label()
        bbox = detection.get_bbox()
        confidence = detection.get_confidence()

        datas['obj_detection'] = [label,confidence,[bbox.xmin(),bbox.ymin(),bbox.xmax(),bbox.ymax()]]

        cls = detection.get_objects_typed(hailo.HAILO_CLASSIFICATION)
        datas['face_detected'] = []
        for i,c in enumerate(cls):
            datas['face_detected'].append([c.get_label(),c.get_confidence()])

        landmarks = detection.get_objects_typed(hailo.HAILO_LANDMARKS)
        points = landmarks[0].get_points()

    # if frame:
        # Note: using imshow will not work here, as the callback function is not running in the main thread
        # Let's print the detection count to the frame
        # cv2.putText(frame, f"Detections: {detection_count}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        # Example of how to use the new_variable and new_function from the user_data
        # Let's print the new_variable and the result of the new_function to the frame
        # cv2.putText(frame, f"{'xxxx'} {'yyyyyy'}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        # Convert the frame to BGR
    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

    # Set the window to fullscreen mode
    cv2.namedWindow("Camera", cv2.WINDOW_NORMAL)
    cv2.setWindowProperty("Camera", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

       
      
    print('\ndatas::::::',datas)
    print('frame::::::',frame.shape)


    #sent data
    # Serialize the metadata to JSON
    json_data = json.dumps(datas)
    json_bytes = json_data.encode()
    # Encode the frame as JPEG and convert to bytes
    _, encoded_frame = cv2.imencode('.jpg', frame)
    frame_bytes = encoded_frame.tobytes()
    # Send size of JSON data (4 bytes)
    json_size = len(json_bytes)
    s.sendall(json_size.to_bytes(4, byteorder='big'))
    # Send the JSON data
    s.sendall(json_bytes)
    # Send size of frame data (4 bytes)
    frame_size = len(frame_bytes)
    s.sendall(frame_size.to_bytes(4, byteorder='big'))
    # Send the actual frame data
    s.sendall(frame_bytes)

    # Add any custom processing logic here
    return Gst.PadProbeReturn.OK

while True:

    if INPUT == 'rpi':
        # Define the GStreamer pipeline
        pipeline_description = f"""
        libcamerasrc ! video/x-raw,format=BGR,width=1536,height=864 ! decodebin ! queue name=hailo_pre_convert_0 leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! 
        videoconvert n-threads=2 qos=false ! queue name=pre_detector_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! tee name=t hailomuxer name=hmux 
        t. ! queue name=detector_bypass_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hmux. 
        t. ! videoscale name=face_videoscale method=0 n-threads=2 add-borders=false qos=false ! video/x-raw, pixel-aspect-ratio=1/1 ! 
        queue name=pre_face_detector_infer_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! 
        hailonet hef-path={RESOURES_PATH}/scrfd_10g.hef scheduling-algorithm=1 vdevice-key=1 ! 
        queue name=detector_post_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! 
        hailofilter so-path={RESOURES_PATH}/libscrfd_post.so name=face_detection_hailofilter qos=false 
        config-path={RESOURES_PATH}/configs/scrfd.json function_name=scrfd_10g ! 
        queue leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hmux. 
        hmux. ! queue name=pre_tracker_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! 
        hailotracker name=hailo_face_tracker class-id=-1 kalman-dist-thr=0.7 iou-thr=0.8 init-iou-thr=0.9 keep-new-frames=2 keep-tracked-frames=6 keep-lost-frames=8 
        keep-past-metadata=true qos=false ! queue name=hailo_post_tracker_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! 
        hailocropper so-path={RESOURES_PATH}/libvms_croppers.so function-name=face_recognition internal-offset=true name=cropper2 hailoaggregator name=agg2 
        cropper2. ! queue name=bypess2_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! agg2. 
        cropper2. ! queue name=pre_face_align_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! 
        hailofilter so-path={RESOURES_PATH}/libvms_face_align.so name=face_align_hailofilter use-gst-buffer=true qos=false ! 
        queue name=detector_pos_face_align_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! 
        hailonet hef-path={RESOURES_PATH}/arcface_mobilefacenet_v1.hef scheduling-algorithm=1 vdevice-key=1 ! 
        queue name=recognition_post_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! 
        hailofilter function-name=arcface_rgb so-path={RESOURES_PATH}/libface_recognition_post.so name=face_recognition_hailofilter qos=false ! 
        queue name=recognition_pre_agg_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! agg2. 
        agg2. ! queue name=hailo_pre_gallery_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! 
        hailogallery gallery-file-path={RESOURES_PATH}/gallery/face_recognition_local_gallery_rgba.json load-local-gallery=true similarity-thr=.4 gallery-queue-size=20 class-id=-1 ! 
        queue name=hailo_pre_draw2 leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! 
        hailooverlay name=hailo_overlay qos=false show-confidence=false local-gallery=true line-thickness=5 font-thickness=2 landmark-point-radius=8 ! 
        queue name=hailo_post_draw leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! 
        videoconvert n-threads=4 qos=false name=display_videoconvert qos=false ! 
        queue name=hailo_display_q_0 leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! 
        fpsdisplaysink video-sink=xvimagesink name=hailo_display sync=false text-overlay=false
        """

    elif INPUT == 'usbcam':
        pipeline_description = f"""v4l2src device=/dev/video0 ! videoconvert n-threads=2 qos=false ! queue name=hailo_pre_convert_0 leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! videoconvert n-threads=2 qos=false ! queue name=pre_detector_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! tee name=t hailomuxer name=hmux t. ! queue name=detector_bypass_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hmux. t. ! videoscale name=face_videoscale method=0 n-threads=2 add-borders=false qos=false ! video/x-raw, pixel-aspect-ratio=1/1 ! queue name=pre_face_detector_infer_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailonet hef-path={RESOURES_PATH}/scrfd_10g.hef scheduling-algorithm=1 vdevice-key=1 ! queue name=detector_post_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailofilter so-path={RESOURES_PATH}/libscrfd_post.so name=face_detection_hailofilter qos=false config-path={RESOURES_PATH}/configs/scrfd.json function_name=scrfd_10g ! queue leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hmux. hmux. ! queue name=pre_tracker_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailotracker name=hailo_face_tracker class-id=-1 kalman-dist-thr=0.7 iou-thr=0.8 init-iou-thr=0.9 keep-new-frames=2 keep-tracked-frames=6 keep-lost-frames=8 keep-past-metadata=true qos=false ! queue name=hailo_post_tracker_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailocropper so-path={RESOURES_PATH}/libvms_croppers.so function-name=face_recognition internal-offset=true name=cropper2 hailoaggregator name=agg2 cropper2. ! queue name=bypess2_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! agg2. cropper2. ! queue name=pre_face_align_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailofilter so-path={RESOURES_PATH}/libvms_face_align.so name=face_align_hailofilter use-gst-buffer=true qos=false ! queue name=detector_pos_face_align_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailonet hef-path={RESOURES_PATH}/arcface_mobilefacenet_v1.hef scheduling-algorithm=1 vdevice-key=1 ! queue name=recognition_post_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailofilter function-name=arcface_rgb so-path={RESOURES_PATH}/libface_recognition_post.so name=face_recognition_hailofilter qos=false ! queue name=recognition_pre_agg_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! agg2. agg2. ! queue name=hailo_pre_gallery_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailogallery gallery-file-path={RESOURES_PATH}/gallery/face_recognition_local_gallery_rgba.json load-local-gallery=true similarity-thr=.4 gallery-queue-size=20 class-id=-1 ! queue name=hailo_pre_draw2 leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailooverlay name=hailo_overlay qos=false show-confidence=false local-gallery=true line-thickness=5 font-thickness=2 landmark-point-radius=8 ! queue name=hailo_post_draw leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! \
                                identity name=identity_callback ! queue name=hailo_display_hailooverlay_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailooverlay name=hailo_display_hailooverlay ! queue name=hailo_display_videoconvert_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! videoconvert name=hailo_display_videoconvert n-threads=2 qos=false ! queue name=hailo_display_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! fpsdisplaysink name=hailo_display video-sink=xvimagesink sync=true text-overlay=false signal-fps-measurements=true
                                """
        
    else:
        pipeline_description = f"""filesrc location={RESOURES_PATH}/face_recognition.mp4 name=src_0 ! decodebin ! queue name=hailo_pre_convert_0 leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! videoconvert n-threads=2 qos=false ! queue name=pre_detector_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! tee name=t hailomuxer name=hmux t. ! queue name=detector_bypass_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hmux. t. ! videoscale name=face_videoscale method=0 n-threads=2 add-borders=false qos=false ! video/x-raw, pixel-aspect-ratio=1/1 ! queue name=pre_face_detector_infer_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailonet hef-path={RESOURES_PATH}/scrfd_10g.hef scheduling-algorithm=1 vdevice-key=1 ! queue name=detector_post_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailofilter so-path={RESOURES_PATH}/libscrfd_post.so name=face_detection_hailofilter qos=false config-path={RESOURES_PATH}/configs/scrfd.json function_name=scrfd_10g ! queue leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hmux. hmux. ! queue name=pre_tracker_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailotracker name=hailo_face_tracker class-id=-1 kalman-dist-thr=0.7 iou-thr=0.8 init-iou-thr=0.9 keep-new-frames=2 keep-tracked-frames=6 keep-lost-frames=8 keep-past-metadata=true qos=false ! queue name=hailo_post_tracker_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailocropper so-path={RESOURES_PATH}/libvms_croppers.so function-name=face_recognition internal-offset=true name=cropper2 hailoaggregator name=agg2 cropper2. ! queue name=bypess2_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! agg2. cropper2. ! queue name=pre_face_align_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailofilter so-path={RESOURES_PATH}/libvms_face_align.so name=face_align_hailofilter use-gst-buffer=true qos=false ! queue name=detector_pos_face_align_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailonet hef-path={RESOURES_PATH}/arcface_mobilefacenet_v1.hef scheduling-algorithm=1 vdevice-key=1 ! queue name=recognition_post_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailofilter function-name=arcface_rgb so-path={RESOURES_PATH}/libface_recognition_post.so name=face_recognition_hailofilter qos=false ! queue name=recognition_pre_agg_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! agg2. agg2. ! queue name=hailo_pre_gallery_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailogallery gallery-file-path={RESOURES_PATH}/gallery/face_recognition_local_gallery_rgba.json load-local-gallery=true similarity-thr=.4 gallery-queue-size=20 class-id=-1 ! queue name=hailo_pre_draw2 leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailooverlay name=hailo_overlay qos=false show-confidence=false local-gallery=true line-thickness=5 font-thickness=2 landmark-point-radius=8 ! queue name=hailo_post_draw leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! \
                                identity name=identity_callback ! queue name=hailo_display_hailooverlay_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailooverlay name=hailo_display_hailooverlay ! queue name=hailo_display_videoconvert_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! videoconvert name=hailo_display_videoconvert n-threads=2 qos=false ! queue name=hailo_display_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! fpsdisplaysink name=hailo_display video-sink=xvimagesink sync=true text-overlay=false signal-fps-measurements=true
                                """


    # Create the GStreamer pipeline
    pipeline = Gst.parse_launch(pipeline_description)

    # Attach the callback to a pad
    filter_element = pipeline.get_by_name("face_detection_hailofilter")
    pad = filter_element.get_static_pad("src")
    if pad:
        pad.add_probe(Gst.PadProbeType.BUFFER, onframe_processed, None)

    # Start the pipeline
    pipeline.set_state(Gst.State.PLAYING)

    # Create a GLib main loop to run the pipeline
    loop = GLib.MainLoop()
    try:
        print("Running the pipeline...")
        loop.run()
    except KeyboardInterrupt:
        print("Stopping the pipeline...")
        loop.quit()

    # Clean up
    pipeline.set_state(Gst.State.NULL)