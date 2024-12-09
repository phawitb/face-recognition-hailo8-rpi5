import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import os
import argparse
import multiprocessing
import numpy as np
import setproctitle
import cv2
import time
import hailo
import subprocess
from hailo_rpi_common import (
    get_default_parser,
    QUEUE,
    SOURCE_PIPELINE,
    INFERENCE_PIPELINE,
    INFERENCE_PIPELINE_WRAPPER,
    USER_CALLBACK_PIPELINE,
    DISPLAY_PIPELINE,
    GStreamerApp,
    app_callback_class,
    dummy_callback,
    detect_hailo_arch,
)

RESOURCES_PATH = "resources"

class GStreamerDetectionApp(GStreamerApp):
    def __init__(self, app_callback, user_data):
        parser = get_default_parser()
        parser.add_argument(
            "--labels-json",
            default=None,
            help="Path to costume labels JSON file",
        )
        args = parser.parse_args()

        print('args',args.input)
        self.source = args.input

        super().__init__(args, user_data)
 
        self.batch_size = 2
        self.network_width = 640
        self.network_height = 640
        self.network_format = "RGB"
        nms_score_threshold = 0.3
        nms_iou_threshold = 0.45

        if args.arch is None:
            detected_arch = detect_hailo_arch()
            if detected_arch is None:
                raise ValueError("Could not auto-detect Hailo architecture. Please specify --arch manually.")
            self.arch = detected_arch
            print(f"Auto-detected Hailo architecture: {self.arch}")
        else:
            self.arch = args.arch

        if args.hef_path is not None:
            self.hef_path = args.hef_path
        # Set the HEF file path based on the arch
        elif self.arch == "hailo8":
            self.hef_path = os.path.join(self.current_path, f'{RESOURCES_PATH}/yolov8m.hef')
        else:  # hailo8l
            self.hef_path = os.path.join(self.current_path, f'{RESOURCES_PATH}/yolov8s_h8l.hef')

        # Set the post-processing shared object file
        self.post_process_so = os.path.join(self.current_path, f'{RESOURCES_PATH}/libyolo_hailortpp_postprocess.so')

        # User-defined label JSON file
        self.labels_json = args.labels_json

        self.app_callback = app_callback

        self.thresholds_str = (
            f"nms-score-threshold={nms_score_threshold} "
            f"nms-iou-threshold={nms_iou_threshold} "
            f"output-format-type=HAILO_FORMAT_TYPE_FLOAT32"
        )

        # Set the process title
        setproctitle.setproctitle("Hailo Detection App")

        self.create_pipeline()

    def get_usb_video_devices(self):
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

    def get_pipeline_string(self):
        source_pipeline = SOURCE_PIPELINE(self.video_source)
        usbcam_port = self.get_usb_video_devices()

        if self.source == 'file':
            pipeline_string = f"""filesrc location={RESOURCES_PATH}/face_recognition.mp4 name=src_0 ! decodebin ! queue name=hailo_pre_convert_0 leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! videoconvert n-threads=2 qos=false ! queue name=pre_detector_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! tee name=t hailomuxer name=hmux t. ! queue name=detector_bypass_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hmux. t. ! videoscale name=face_videoscale method=0 n-threads=2 add-borders=false qos=false ! video/x-raw, pixel-aspect-ratio=1/1 ! queue name=pre_face_detector_infer_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailonet hef-path={RESOURCES_PATH}/scrfd_10g.hef scheduling-algorithm=1 vdevice-key=1 ! queue name=detector_post_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailofilter so-path={RESOURCES_PATH}/libscrfd_post.so name=face_detection_hailofilter qos=false config-path={RESOURCES_PATH}/configs/scrfd.json function_name=scrfd_10g ! queue leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hmux. hmux. ! queue name=pre_tracker_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailotracker name=hailo_face_tracker class-id=-1 kalman-dist-thr=0.7 iou-thr=0.8 init-iou-thr=0.9 keep-new-frames=2 keep-tracked-frames=6 keep-lost-frames=8 keep-past-metadata=true qos=false ! queue name=hailo_post_tracker_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailocropper so-path={RESOURCES_PATH}/libvms_croppers.so function-name=face_recognition internal-offset=true name=cropper2 hailoaggregator name=agg2 cropper2. ! queue name=bypess2_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! agg2. cropper2. ! queue name=pre_face_align_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailofilter so-path={RESOURCES_PATH}/libvms_face_align.so name=face_align_hailofilter use-gst-buffer=true qos=false ! queue name=detector_pos_face_align_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailonet hef-path={RESOURCES_PATH}/arcface_mobilefacenet_v1.hef scheduling-algorithm=1 vdevice-key=1 ! queue name=recognition_post_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailofilter function-name=arcface_rgb so-path={RESOURCES_PATH}/libface_recognition_post.so name=face_recognition_hailofilter qos=false ! queue name=recognition_pre_agg_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! agg2. agg2. ! queue name=hailo_pre_gallery_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailogallery gallery-file-path={RESOURCES_PATH}/gallery/face_recognition_local_gallery_rgba.json load-local-gallery=true similarity-thr=.4 gallery-queue-size=20 class-id=-1 ! queue name=hailo_pre_draw2 leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailooverlay name=hailo_overlay qos=false show-confidence=false local-gallery=true line-thickness=5 font-thickness=2 landmark-point-radius=8 ! queue name=hailo_post_draw leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! \
                            identity name=identity_callback ! queue name=hailo_display_hailooverlay_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailooverlay name=hailo_display_hailooverlay ! queue name=hailo_display_videoconvert_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! videoconvert name=hailo_display_videoconvert n-threads=2 qos=false ! queue name=hailo_display_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! fpsdisplaysink name=hailo_display video-sink=xvimagesink sync=true text-overlay=false signal-fps-measurements=true
                            """
        elif self.source == 'rpi':
            pipeline_string = f"""
                libcamerasrc ! video/x-raw,format=BGR,width=1536,height=864 ! decodebin ! queue name=hailo_pre_convert_0 leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! 
                videoconvert n-threads=2 qos=false ! queue name=pre_detector_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! 
                tee name=t hailomuxer name=hmux 
                t. ! queue name=detector_bypass_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hmux. 
                t. ! queue name=pre_face_detector_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! 
                videoscale name=face_videoscale method=0 n-threads=2 add-borders=false qos=false ! video/x-raw, pixel-aspect-ratio=1/1 ! 
                queue name=pre_face_detector_infer_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! 
                hailonet hef-path={RESOURCES_PATH}/scrfd_10g.hef scheduling-algorithm=1 vdevice-key=1 ! 
                queue name=detector_post_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! 
                hailofilter so-path={RESOURCES_PATH}/libscrfd_post.so name=face_detection_hailofilter qos=false 
                config-path={RESOURCES_PATH}/configs/scrfd.json function_name=scrfd_10g ! 
                hailotracker name=hailo_face_tracker class-id=-1 kalman-dist-thr=0.7 iou-thr=0.8 init-iou-thr=0.9 keep-new-frames=2 keep-tracked-frames=6 keep-lost-frames=8 
                keep-past-metadata=true qos=false ! queue name=hailo_post_tracker_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! 
                hailocropper so-path={RESOURCES_PATH}/libvms_croppers.so function-name=face_recognition internal-offset=true name=cropper2 hailoaggregator name=agg2 
                cropper2. ! queue name=bypess2_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! agg2. 
                cropper2. ! queue name=pre_face_align_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! 
                hailofilter so-path={RESOURCES_PATH}/libvms_face_align.so name=face_align_hailofilter use-gst-buffer=true qos=false ! 
                queue name=detector_pos_face_align_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! 
                hailonet hef-path={RESOURCES_PATH}/arcface_mobilefacenet_v1.hef scheduling-algorithm=1 vdevice-key=1 ! 
                queue name=recognition_post_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! 
                hailofilter function-name=arcface_rgb so-path={RESOURCES_PATH}/libface_recognition_post.so name=face_recognition_hailofilter qos=false ! 
                queue name=recognition_pre_agg_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! agg2. 
                agg2. ! queue name=hailo_pre_gallery_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! 
                hailogallery gallery-file-path={RESOURCES_PATH}/gallery/face_recognition_local_gallery_rgba.json load-local-gallery=true similarity-thr=.4 gallery-queue-size=20 class-id=-1 ! 
                identity name=identity_callback ! 
                queue leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! hmux. 
                hmux. ! queue name=pre_tracker_q leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! 
                queue name=hailo_pre_draw2 leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! 
                hailooverlay name=hailo_overlay qos=false show-confidence=false local-gallery=true line-thickness=5 font-thickness=2 landmark-point-radius=8 ! 
                queue name=hailo_post_draw leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! 
                videoconvert n-threads=4 qos=false name=display_videoconvert qos=false ! 
                queue name=hailo_display_q_0 leaky=no max-size-buffers=30 max-size-bytes=0 max-size-time=0 ! 
                fpsdisplaysink video-sink=fakesink name=hailo_display sync=false text-overlay=false
                """

        elif self.source == 'usbcam' and usbcam_port:
            pipeline_string = f"""v4l2src device={usbcam_port[0]} ! videoconvert n-threads=2 qos=false ! queue name=hailo_pre_convert_0 leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! videoconvert n-threads=2 qos=false ! queue name=pre_detector_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! tee name=t hailomuxer name=hmux t. ! queue name=detector_bypass_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hmux. t. ! videoscale name=face_videoscale method=0 n-threads=2 add-borders=false qos=false ! video/x-raw, pixel-aspect-ratio=1/1 ! queue name=pre_face_detector_infer_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailonet hef-path={RESOURCES_PATH}/scrfd_10g.hef scheduling-algorithm=1 vdevice-key=1 ! queue name=detector_post_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailofilter so-path={RESOURCES_PATH}/libscrfd_post.so name=face_detection_hailofilter qos=false config-path={RESOURCES_PATH}/configs/scrfd.json function_name=scrfd_10g ! queue leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hmux. hmux. ! queue name=pre_tracker_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailotracker name=hailo_face_tracker class-id=-1 kalman-dist-thr=0.7 iou-thr=0.8 init-iou-thr=0.9 keep-new-frames=2 keep-tracked-frames=6 keep-lost-frames=8 keep-past-metadata=true qos=false ! queue name=hailo_post_tracker_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailocropper so-path={RESOURCES_PATH}/libvms_croppers.so function-name=face_recognition internal-offset=true name=cropper2 hailoaggregator name=agg2 cropper2. ! queue name=bypess2_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! agg2. cropper2. ! queue name=pre_face_align_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailofilter so-path={RESOURCES_PATH}/libvms_face_align.so name=face_align_hailofilter use-gst-buffer=true qos=false ! queue name=detector_pos_face_align_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailonet hef-path={RESOURCES_PATH}/arcface_mobilefacenet_v1.hef scheduling-algorithm=1 vdevice-key=1 ! queue name=recognition_post_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailofilter function-name=arcface_rgb so-path={RESOURCES_PATH}/libface_recognition_post.so name=face_recognition_hailofilter qos=false ! queue name=recognition_pre_agg_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! agg2. agg2. ! queue name=hailo_pre_gallery_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailogallery gallery-file-path={RESOURCES_PATH}/gallery/face_recognition_local_gallery_rgba.json load-local-gallery=true similarity-thr=.4 gallery-queue-size=20 class-id=-1 ! queue name=hailo_pre_draw2 leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailooverlay name=hailo_overlay qos=false show-confidence=false local-gallery=true line-thickness=5 font-thickness=2 landmark-point-radius=8 ! queue name=hailo_post_draw leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! \
                            identity name=identity_callback ! queue name=hailo_display_hailooverlay_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! hailooverlay name=hailo_display_hailooverlay ! queue name=hailo_display_videoconvert_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! videoconvert name=hailo_display_videoconvert n-threads=2 qos=false ! queue name=hailo_display_q leaky=no max-size-buffers=3 max-size-bytes=0 max-size-time=0 ! fpsdisplaysink name=hailo_display video-sink=fakesink sync=true text-overlay=false signal-fps-measurements=true
                            """

        print(pipeline_string)

        return pipeline_string

if __name__ == "__main__":
    user_data = app_callback_class()
    app_callback = dummy_callback
    app = GStreamerDetectionApp(app_callback, user_data)
    app.run()
