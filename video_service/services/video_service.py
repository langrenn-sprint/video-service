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
        error_count = 0
        # Update status and return result
        await StatusAdapter().create_status(
            token,
            event,
            status_type,
            f"Initiating video capture. Input FPS {frame_rate}, output FPS: {video_clip_fps}.",
        )

        try:
            while True:
                clip_count += 1
                captured = self.capture_video_clip(
                    video_capture,
                    video_file_path,
                    video_clip_fps,
                    image_size,
                    frame_interval,
                    frames_per_clip,
                    clip_count,
                )
                if not captured:
                    error_count += 1

                continue_tracking = await ConfigAdapter().get_config_bool(
                    token, event["id"], "CAPTURE_VIDEO_SERVICE_START"
                )
                if not continue_tracking:
                    break  # No more frames to process

        finally:
            video_capture.release()
            await ConfigAdapter().update_config(
                token, event["id"], "CAPTURE_VIDEO_SERVICE_RUNNING", "False"
            )

        # Update status and return result
        informasjon = f"Video capture completed: {clip_count} clips saved, {error_count} errors."
        await StatusAdapter().create_status(
            token,
            event,
            status_type,
            informasjon,
        )
        return informasjon

    def capture_video_clip(
        self,
        video_capture: cv2.VideoCapture,
        video_file_path: str,
        video_clip_fps: int,
        image_size: tuple,
        frame_interval: int,
        frames_per_clip: int,
        clip_count: int,
    ) -> bool:
        """Capture a video clip from the video stream.

        Args:
            video_capture: OpenCV VideoCapture object.
            video_file_path: Path to save the video clip.
            video_clip_fps: Frames per second for the video clip.
            image_size: Size of the video frames.
            frame_interval: Interval between frames to capture.
            frames_per_clip: Total number of frames in the clip.
            clip_count: Current clip count.

        Returns:
            bool: True if the clip was successfully captured, False otherwise.

        """
        clip_frames = []
        frame_idx = 0
        for frame_idx in range(frames_per_clip):
            ret, frame = video_capture.read()
            if not ret:
                break  # End of video stream

            if frame_idx % frame_interval == 0:
                clip_frames.append(frame)

        if clip_frames:
            # Save the clip to a file
            timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%S")
            base = Path(video_file_path)
            tmp_path = base / f"TMP_CAPTURED_{timestamp}_{clip_count}.mp4"
            final_path = base / f"CAPTURED{timestamp}_{clip_count}.mp4"
            clip_count += 1

            # Define the codec and create a VideoWriter object
            fourcc = cv2.VideoWriter.fourcc(*"mp4v")
            out = cv2.VideoWriter(str(tmp_path), fourcc, video_clip_fps, image_size)

            if not out.isOpened():
                out.release()
                logging.exception("VideoWriter failed to open for %s", str(tmp_path))
                return False

            try:
                for frame in clip_frames:
                    out.write(frame)
            finally:
                out.release()

            try:
                tmp_path.replace(final_path)
            except Exception:
                logging.exception("Failed to rename %s to %s", tmp_path, final_path)
                return False
        return True

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

        """
        # Open the video stream for captured video clips
        video_urls = PhotosFileAdapter().get_all_capture_files(event["id"], storage_mode)
        if video_urls:
            await ConfigAdapter().update_config(
                token, event["id"], "DETECT_VIDEO_SERVICE_RUNNING", "True"
            )
            video_settings = await self.get_video_settings(token, event)
            for video_stream_url in video_urls:
                try:
                    url_list = self.detect_crossings_with_ultraltyics(event, video_stream_url["url"], video_settings)
                    if url_list:
                        await ConfigAdapter().update_config(
                            token, event["id"], "LATEST_DETECTED_PHOTO_URL", url_list[0]
                        )
                    archive_file = PhotosFileAdapter().move_to_capture_archive(event["id"], storage_mode, Path(video_stream_url["name"]).name)
                    informasjon = f" Deteksjoner: <a href='{archive_file}'>video</a>, {len(url_list)} passeringer."
                except VideoStreamNotFoundError as e:
                    error_file = PhotosFileAdapter().move_to_error_archive(event["id"], storage_mode, Path(video_stream_url["name"]).name)
                    informasjon = f"Error processing stream from: {error_file} - details: {e!s}"
                    logging.exception(informasjon)
                await StatusAdapter().create_status(
                    token, event, "VIDEO_ANALYTICS", informasjon
                )

            # Update status and return result
            await ConfigAdapter().update_config(
                token, event["id"], "DETECT_VIDEO_SERVICE_RUNNING", "false"
            )
        return f"Crossings detection completed, processed {len(video_urls)} videos."

    def detect_crossings_with_ultraltyics(
        self,
        event: dict,
        video_stream_url: str,
        video_settings: dict,
    ) -> list:
        """Analyze video and capture screenshots of line crossings.

        Args:
            token: To update databes
            event: Event details
            video_stream_url: Url to the video stream to analyze.
            video_settings: Video settings from config.

        Returns:
            A list with public URLs to all detections.

        Raises:
            VideoStreamNotFoundError: If the video stream cannot be found.

        """
        crossings = {"100": [], "90": {}, "80": {}}

        # Load an official or custom model
        model = YOLO(video_settings["yolo_model_name"])  # Load an official Detect model


        # Perform tracking with the model
        try:
            results = model.track(
                source=video_stream_url,
                conf=MIN_CONFIDENCE,
                classes=DETECTION_CLASSES,
                stream=True,
                imgsz=video_settings["image_size"],
                persist=True
            )
        except Exception as e:
            informasjon = f"Error opening video stream from: {video_stream_url}"
            logging.exception(informasjon)
            raise VideoStreamNotFoundError(informasjon) from e

        url_list = []
        for frame_number, result in enumerate(results, start=1):
            detections = VisionAIService().process_boxes(
                event["id"], result, video_settings["trigger_line"], crossings, video_settings["camera_location"], frame_number, video_settings["fps"], video_settings["min_confidence"]
            )
            if detections:
                url_list.extend(detections)

        return url_list

    async def get_video_settings(
        self,
        token: str,
        event: dict,
    ) -> dict:
        """Get video settings from config.

        Args:
            token: To access database
            event: Event details

        Returns:
            A dict with video settings.

        """
        video_settings = {}
        video_settings["camera_location"] = await ConfigAdapter().get_config(
            token, event["id"], "CAMERA_LOCATION"
        )
        video_settings["fps"] = await ConfigAdapter().get_config_int(token, event["id"], "VIDEO_CLIP_FPS")

        video_settings["yolo_model_name"] = await ConfigAdapter().get_config(
            token, event["id"], "YOLO_MODEL_NAME"
        )
        video_settings["image_size"] = await ConfigAdapter().get_config_img_res_tuple(
            token, event["id"], "DETECT_ANALYTICS_IMAGE_SIZE"
        )
        video_settings["trigger_line"] = (
            await VisionAIService().get_trigger_line_xyxy_list(
                token, event
            )
        )
        video_settings["min_confidence"] = float(await ConfigAdapter().get_config(
            token, event["id"], "DETECTION_CONFIDENCE_THRESHOLD"
        ))
        return video_settings
