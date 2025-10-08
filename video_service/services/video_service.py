"""Module for video services."""

import datetime
import logging
from pathlib import Path

import cv2
from ultralytics import YOLO
from ultralytics.engine.results import Results

from video_service.adapters import (
    ConfigAdapter,
    PhotosFileAdapter,
    StatusAdapter,
    VideoStreamNotFoundError,
)
from video_service.adapters.google_cloud_storage_adapter import (
    GoogleCloudStorageAdapter,
)
from video_service.services.vision_ai_service import (
    VisionAIService,
)

DETECTION_CLASSES = [0]  # person
MIN_CONFIDENCE = 0.6

class VideoService:
    """Class representing video service."""

    async def capture_video(
        self,
        token: str,
        event: dict,
        status_type: str,
    ) -> str:
        """Capture video from a stream, save the video to a file, each clip 15 seconsds long.

        The video is saved in the specified directory with a timestamp in the filename.

        Args:
            token: To update databes
            event: Event details
            status_type: To update status messages

        Returns:
            A string indicating the status of the video analytics.

        Raises:
            VideoStreamNotFoundError: If the video stream cannot be found.

        """
        mode = "CAPTURE"
        informasjon = ""
        video_stream_url = await ConfigAdapter().get_config(token, event["id"], "VIDEO_URL")
        video_clip_fps = await ConfigAdapter().get_config_int(token, event["id"], "VIDEO_CLIP_FPS")
        video_file_path = PhotosFileAdapter().get_capture_folder_path()

        clip_duration = await ConfigAdapter().get_config_int(
            token, event["id"], "VIDEO_CLIP_DURATION"
        )
        # Open the video stream
        video_capture = cv2.VideoCapture(video_stream_url)
        if not video_capture.isOpened():
            informasjon = f"Error opening video stream from: {video_stream_url}"
            logging.exception(informasjon)
            raise VideoStreamNotFoundError(informasjon)

        width = int(video_capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(video_capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        image_size = (width, height)
        frame_rate = int(video_capture.get(cv2.CAP_PROP_FPS))  # Get the frame rate of the video
        frame_interval = max(1, round(frame_rate / video_clip_fps))
        frames_per_clip = frame_rate * clip_duration  # Calculate the number of frames for a 15-second clip
        clip_count = 0
        # Update status and return result
        await StatusAdapter().create_status(
            token,
            event,
            status_type,
            f"Initiating video capture. Input FPS {frame_rate}, output FPS: {video_clip_fps}.",
        )

        try:
            while True:
                clip_frames = []
                frame_idx = 0
                for frame_idx in range(frames_per_clip):
                    ret, frame = video_capture.read()
                    if not ret:
                        break  # End of video stream

                    if frame_idx % frame_interval == 0:
                        clip_frames.append(frame)

                if not clip_frames:
                    break  # No more frames to process

                # Save the clip to a file
                timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%S")
                clip_filename = f"{video_file_path}/CAPTURED_{timestamp}_{clip_count}.mp4"
                clip_count += 1

                # Define the codec and create a VideoWriter object
                fourcc = cv2.VideoWriter.fourcc(*"mp4v")
                out = cv2.VideoWriter(clip_filename, fourcc, video_clip_fps, image_size)

                for frame in clip_frames:
                    out.write(frame)
                out.release()

                continue_tracking = await ConfigAdapter().get_config_bool(
                    token, event["id"], f"{mode}_VIDEO_SERVICE_START"
                )
                if not continue_tracking:
                    break  # No more frames to process

        finally:
            video_capture.release()
            await ConfigAdapter().update_config(
                token, event["id"], f"{mode}_VIDEO_SERVICE_RUNNING", "False"
            )

        # Update status and return result
        await StatusAdapter().create_status(
            token,
            event,
            status_type,
            f"Video capture: {clip_count} clips saved.",
        )
        return f"Video capture: {clip_count} clips saved."


    async def detect_crossings(
        self,
        token: str,
        event: dict,
        storage_mode: str,
    ) -> str:
        """Detect crossing video from detected video clips.

        Screenshots with crossings are taken. The video archived.

        Args:
            token: To update database
            event: Event details
            storage_mode: Storage mode for the video clips

        Returns:
            A string indicating the status of the video analytics.

        Raises:
            VideoStreamNotFoundError: If the video stream cannot be found.

        """
        mode = "DETECT"

        # Open the video stream for captured video clips
        video_urls = PhotosFileAdapter().get_all_capture_files(event["id"], storage_mode)
        if video_urls:
            await ConfigAdapter().update_config(
                token, event["id"], f"{mode}_VIDEO_SERVICE_RUNNING", "True"
            )
        for video_stream_url in video_urls:
            informasjon = await self.detect_crossings_with_ultraltyics(token, event, video_stream_url["url"])
            archive_file = PhotosFileAdapter().move_to_capture_archive(event["id"], storage_mode, Path(video_stream_url["name"]).name)
            informasjon += f" Kilde: <a href='{archive_file}'>video</a>, "
            await StatusAdapter().create_status(
                token, event, "VIDEO_ANALYTICS", informasjon
            )

        # Update status and return result
        await ConfigAdapter().update_config(
            token, event["id"], f"{mode}_VIDEO_SERVICE_RUNNING", "False"
        )
        return "Crossings detection completed."

    async def detect_crossings_with_ultraltyics(
        self,
        token: str,
        event: dict,
        video_stream_url: str,
    ) -> str:
        """Analyze video and capture screenshots of line crossings.

        Args:
            token: To update databes
            event: Event details
            video_stream_url: Url to the video stream to analyze.

        Returns:
            A string indicating the status of the video analytics.

        Raises:
            VideoStreamNotFoundError: If the video stream cannot be found.

        """
        crossings = {"100": [], "90": {}, "80": {}}
        informasjon = ""
        camera_location = await ConfigAdapter().get_config(
            token, event["id"], "CAMERA_LOCATION"
        )
        fps = await ConfigAdapter().get_config_int(token, event["id"], "VIDEO_CLIP_FPS")

        yolo_model_name = await ConfigAdapter().get_config(
            token, event["id"], "YOLO_MODEL_NAME"
        )
        # Load an official or custom model
        model = YOLO(yolo_model_name)  # Load an official Detect model

        # Define the desired image size as a tuple (width, height)
        image_size = await ConfigAdapter().get_config_img_res_tuple(
            token, event["id"], "DETECT_ANALYTICS_IMAGE_SIZE"
        )
        trigger_line = (
            await VisionAIService().get_trigger_line_xyxy_list(
                token, event
            )
        )
        await ConfigAdapter().update_config(
            token, event["id"], "DETECT_VIDEO_SERVICE_RUNNING", "True"
        )

        # Perform tracking with the model
        try:
            results = model.track(
                source=video_stream_url,
                conf=MIN_CONFIDENCE,
                classes=DETECTION_CLASSES,
                stream=True,
                imgsz=image_size,
                persist=True
            )
        except Exception as e:
            informasjon = f"Error opening video stream from: {video_stream_url}"
            logging.exception(informasjon)
            raise VideoStreamNotFoundError(informasjon) from e

        url_list = []
        for frame_number, result in enumerate(results, start=1):
            detections = VisionAIService().process_boxes(
                event["id"], result, trigger_line, crossings, camera_location, frame_number, fps
            )
            if detections:
                url_list.extend(detections)

        await ConfigAdapter().update_config(
            token, event["id"], "DETECT_VIDEO_SERVICE_RUNNING", "false"
        )
        informasjon = f"Analytics: {len(url_list)} detections. {informasjon}"
        for url in url_list:
            informasjon += f" <a href='{url}'>klikk</a>, "
        return informasjon

