"""Module for video services."""

import asyncio
import datetime
import logging
import os
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO
from ultralytics.engine.results import Results

from video_service.adapters import (
    ConfigAdapter,
    GCSLockAdapter,
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
        instance_name: str,
    ) -> str:
        """Capture video from a stream, save the video to a file, each clip 15 seconsds long.

        The video is saved in the specified directory with a timestamp in the filename.

        Args:
            token: To update databes
            event: Event details
            status_type: To update status messages
            instance_name: Name of the instance running the service

        Returns:
            A string indicating the status of the video analytics.

        Raises:
            VideoStreamNotFoundError: If the video stream cannot be found.

        """
        informasjon = ""
        video_stream_url = await ConfigAdapter().get_config(token, event["id"], "VIDEO_URL")
        video_file_path = PhotosFileAdapter().get_raw_capture_folder_path()

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
        frames_per_clip = frame_rate * clip_duration  # Calculate the number of frames for a 15-second clip
        clip_count = 0
        error_count = 0
        # Update status and return result
        await StatusAdapter().create_status(
            token,
            event,
            status_type,
            f"{instance_name}: Initiating video capture. Input FPS {frame_rate}.",
        )

        video_settings = {
            "video_file_path": video_file_path,
            "frame_rate": frame_rate,
            "image_size": image_size,
            "frames_per_clip": frames_per_clip,
        }

        try:
            clip_count, error_count = await self.capture_video_clip(
                token,
                event,
                video_capture,
                video_settings,
            )
            await StatusAdapter().create_status(
                token,
                event,
                status_type,
                f"{instance_name}: Captured {clip_count} clips.",
            )

        finally:
            video_capture.release()
            await ConfigAdapter().update_config(
                token, event["id"], "CAPTURE_VIDEO_SERVICE_RUNNING", "False"
            )

        # Update status and return result
        informasjon = f"{instance_name}: {clip_count} clips saved, {error_count} errors."
        await StatusAdapter().create_status(
            token,
            event,
            status_type,
            informasjon,
        )
        return informasjon

    async def capture_video_clip(
        self,
        token: str,
        event: dict,
        video_capture: cv2.VideoCapture,
        video_settings: dict,
    ) -> tuple:
        """Capture a video clip from the video stream.

        Args:
            token: To update databes
            event: Event details
            video_capture: OpenCV VideoCapture object.
            video_settings: dict, video settings from config.

        Returns:
            tuple: A tuple containing number of clips captured and errors encountered.

        """
        clip_frames = []
        clip_count = 0
        error_count = 0
        max_errors = 10
        consecutive_error_count = 0
        max_consecutive_errors = 10
        background_tasks = []  # Keep track of background write tasks

        while True:
            t_start = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%S")

            for _ in range(video_settings["frames_per_clip"]):
                ret, frame = video_capture.read()
                if ret:
                    clip_frames.append(frame)
                    consecutive_error_count = 0
                else:
                    consecutive_error_count += 1
                if consecutive_error_count >= max_consecutive_errors:
                    logging.error("Maximum consecutive error count reached: %d", consecutive_error_count)
                    error_count += 1
                    break

            t_stop = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%S")

            if clip_frames:
                # Save the clip to a file
                base = Path(video_settings["video_file_path"])
                tmp_path = base / f"TMP_CAPTURED_{t_start}_{clip_count}.mp4"
                final_path = base / f"CAPTURED_{t_start}_{clip_count}.mp4"

                # Deep copy frames to avoid mutations
                frames_copy = [frame.copy() for frame in clip_frames]

                # Spin off write task without waiting
                task = asyncio.create_task(
                    self.write_frames_async(frames_copy, video_settings, tmp_path, final_path)
                )
                background_tasks.append(task)

                # Clear clip_frames for next iteration
                clip_frames_count = len(clip_frames)
                clip_frames = []
                clip_count += 1

                capture_timing = {
                    "t_start": t_start,
                    "t_stop": t_stop,
                    "t_finalize": datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%S"),
                }
                logging.info("Captured clip %d with %d frames and timing: %s", clip_count, clip_frames_count, capture_timing)

            continue_tracking = await ConfigAdapter().get_config_bool(
                token, event["id"], "CAPTURE_VIDEO_SERVICE_START"
            )
            if not continue_tracking:
                break  # No more frames to process
            if error_count >= max_errors:
                logging.error("Maximum error count reached: %d", error_count)
                break

        # Wait for all background write tasks to complete before returning
        if background_tasks:
            logging.info("Waiting for %d background write tasks to complete", len(background_tasks))
            await asyncio.gather(*background_tasks, return_exceptions=True)


        return (clip_count, error_count)

    async def write_frames_async(
        self,
        frames: list[np.ndarray],
        video_settings: dict,
        tmp_path: Path,
        final_path: Path
    ) -> None:
        """Write frames to video writer asynchronously."""
        # Define the codec and create a VideoWriter object
        fourcc = cv2.VideoWriter.fourcc(*"mp4v")
        writer = cv2.VideoWriter(
            str(tmp_path),
            fourcc,
            video_settings["frame_rate"],
            video_settings["image_size"]
        )
        if not writer.isOpened():
            writer.release()
            informasjon = f"VideoWriter failed to open: {tmp_path}"
            raise RuntimeError(informasjon)

        try:
            for frame in frames:
                writer.write(frame)
        finally:
            writer.release()
        try:
            tmp_path.replace(final_path)
        except Exception:
            logging.exception("Failed to rename %s to %s", tmp_path, final_path)
        logging.info("Saved video clip to %s", final_path)

    async def detect_crossings_local_storage(
        self,
        token: str,
        event: dict,
    ) -> str:
        """Detect crossing video from detected video clips - local storage.

        Screenshots with crossings are taken. The video archived.

        Args:
            token: To update database
            event: Event details

        Returns:
            A string indicating the status of the video analytics.

        """
        # Open the video stream for captured video clips
        video_urls = PhotosFileAdapter().get_capture_files(event["id"], "local_storage")

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
                    PhotosFileAdapter().move_to_capture_archive(event["id"], "local_storage", Path(video_stream_url["name"]).name)
                    informasjon = f" Video <a href='{video_stream_url["url"]}'>{Path(video_stream_url["name"]).name}</a>, {len(url_list)} passeringer."
                except VideoStreamNotFoundError as e:
                    error_file = PhotosFileAdapter().move_to_error_archive(event["id"], "local_storage", Path(video_stream_url["name"]).name)
                    informasjon = f"Error processing stream from: {error_file} - details: {e!s}"
                    logging.exception(informasjon)
                await StatusAdapter().create_status(
                    token, event, "VIDEO_ANALYTICS", informasjon
                )

            # Update status and return result
            await ConfigAdapter().update_config(
                token, event["id"], "DETECT_VIDEO_SERVICE_RUNNING", "False"
            )
        return f"Crossings detection completed, processed {len(video_urls)} videos."

    async def detect_crossings_cloud_storage(
        self,
        token: str,
        event: dict,
        instance_name: str,
    ) -> str:
        """Detect crossing video from detected video clips. Storage mode is cloud storage.

        Screenshots with crossings are taken. The video archived.

        Args:
            token: To update database
            event: Event details
            storage_mode: Storage mode for the video clips
            instance_name: Name of the service instance.

        Returns:
            A string indicating the status of the video analytics.

        """
        video_count = 0
        await ConfigAdapter().update_config(
            token, event["id"], "DETECT_VIDEO_SERVICE_RUNNING", "True"
        )

        while True:
            # Open the video stream for captured video clips
            video_url = PhotosFileAdapter().get_unlocked_capture_file(event["id"])

            if video_url:
                video_count += 1
                video_settings = await self.get_video_settings(token, event)
                # lock video file - only on cloud storage mode
                instance_id = f"instance-{os.getpid()}"
                file_locked = GCSLockAdapter().try_acquire_lock(video_url["name"], instance_id)
                if not file_locked:
                    logging.info("Video file is locked by another instance, skipping: %s", video_url["name"])
                    continue  # Skip processing this file

                try:
                    url_list = self.detect_crossings_with_ultraltyics(event, video_url["url"], video_settings)
                    if url_list:
                        await ConfigAdapter().update_config(
                            token, event["id"], "LATEST_DETECTED_PHOTO_URL", url_list[0]
                        )
                    PhotosFileAdapter().move_to_capture_archive(event["id"], "cloud_storage", Path(video_url["name"]).name)
                    informasjon = f" {instance_name}: {Path(video_url["name"]).name}, {len(url_list)} passeringer."
                except VideoStreamNotFoundError as e:
                    error_file = PhotosFileAdapter().move_to_error_archive(event["id"], "cloud_storage", Path(video_url["name"]).name)
                    informasjon = f"{instance_name}: Error processing stream from: {error_file} - details: {e!s}"
                    logging.exception(informasjon)
                finally:
                    # Always release lock
                    GCSLockAdapter().release_lock(video_url["name"])
                await StatusAdapter().create_status(
                    token, event, "VIDEO_ANALYTICS", informasjon
                )
            else:
                # No more videos to process
                break

        # Update status and return result
        await ConfigAdapter().update_config(
            token, event["id"], "DETECT_VIDEO_SERVICE_RUNNING", "False"
        )
        return f"Crossings detection completed, processed {video_count} videos."

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
                event["id"], result, video_settings["trigger_line"], crossings, video_settings["camera_location"], frame_number, video_settings["min_confidence"]
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
