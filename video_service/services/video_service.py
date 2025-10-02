"""Module for video services."""

import datetime
import logging
import math
from collections import defaultdict
from pathlib import Path

import cv2
from torch import Tensor
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


    async def filter_video(
        self,
        token: str,
        event: dict,
        status_type: str,
        storage_mode: str,
    ) -> str:
        """Filter video clips, remove unwanted frames.

        The video is saved in the specified directory with a timestamp in the filename.

        Args:
            token: To update database
            event: Event details
            status_type: To update status messages
            storage_mode: To determine if video clips are stored locally or in the cloud

        Returns:
            A string indicating the status of the video analytics.

        Raises:
            VideoStreamNotFoundError: If the video stream cannot be found.

        """
        mode = "FILTER"

        clip_count = 0
        frame_count = 0

        # Discover video URLs/files
        captured_videos = await self._list_captured_videos(storage_mode)
        if captured_videos:
            max_clips = await ConfigAdapter().get_config_int(
                token, event["id"], "MAX_CLIPS_PER_FILTERED_VIDEO"
            )
            await ConfigAdapter().update_config(
                token, event["id"], f"{mode}_VIDEO_SERVICE_RUNNING", "True"
            )

            model = YOLO(await ConfigAdapter().get_config(
                token, event["id"], "YOLO_MODEL_NAME"
            ))
            image_size = await ConfigAdapter().get_config_img_res_tuple(
                token, event["id"], "DETECT_ANALYTICS_IMAGE_SIZE"
            )
            video_stream_detections = []

            for video in captured_videos:
                # respect the max clip limit
                if clip_count > max_clips:
                    break
                clip_count += 1

                crossings_summary = await self._process_single_video(
                    model, video, token, event, frame_count, image_size
                )
                video_stream_detections.append(crossings_summary)

            # Save the relevant clips to a new video file
            segments = []
            video_index = 0
            for detection in video_stream_detections:
                video_index += 1
                segments.append(detection)
                if detection["crossings"]["last_frame"] < detection["crossings"]["total_frames"]:
                    self._concatenate_video_segments(segments, storage_mode)
                    segments.clear()
                    video_index = 0

            if segments:
                # in case some segments are left after the loop
                clip_count = clip_count - len(segments)

            # Update status and return result
            await ConfigAdapter().update_config(
                token, event["id"], f"{mode}_VIDEO_SERVICE_RUNNING", "False"
            )
            if clip_count > 0:
                await StatusAdapter().create_status(
                    token,
                    event,
                    status_type,
                    f"Video filter: {clip_count} clips saved.",
                )

        return f"Video filter: {clip_count} clips saved."


    async def detect_crossings(
        self,
        token: str,
        event: dict,
    ) -> str:
        """Detect crossing video from filterd video clips.

        Screenshots with crossings are taken. The video archived.

        Args:
            token: To update database
            event: Event details

        Returns:
            A string indicating the status of the video analytics.

        Raises:
            VideoStreamNotFoundError: If the video stream cannot be found.

        """
        mode = "DETECT"

        # Open the video stream for filterd video clips
        video_urls = PhotosFileAdapter().get_all_filter_files()
        if video_urls:
            await ConfigAdapter().update_config(
                token, event["id"], f"{mode}_VIDEO_SERVICE_RUNNING", "True"
            )
        for video_stream_url in video_urls:
            await self.detect_crossings_with_ultraltyics(token, event, video_stream_url)
            PhotosFileAdapter().move_to_filter_archive(Path(video_stream_url).name)


        # Update status and return result
        await ConfigAdapter().update_config(
            token, event["id"], f"{mode}_VIDEO_SERVICE_RUNNING", "False"
        )
        return "Crossings detection completed."

    def get_crossings_summary(self, crossings: list) -> dict:
        """Analyze crossings and get overview of frames with relevant information."""
        crossings_summary = {
            "min_persons": 0,
            "max_persons": 0,
            "last_frame": 0,
            "total_frames": 0,
        }
        i_count = 0
        i_last_detection = 0

        # get overview of persons moving - purpose is to ignore persons that are not moving
        filtered_crossings = self.filter_crossings(crossings)

        for crossing in filtered_crossings:
            i_count += 1
            crossings_summary["max_persons"] = max(crossings_summary["max_persons"], crossing["persons_count"])
            crossings_summary["min_persons"] = min(crossings_summary["min_persons"], crossing["persons_count"])
            if crossing["persons_count"] > 0:
                i_last_detection = i_count
        crossings_summary["last_frame"] = i_last_detection
        crossings_summary["total_frames"] = i_count
        return crossings_summary

    def _concatenate_video_segments(self, video_segments: list, storage_mode: str) -> None:
        """Concatenate segments from multiple videos into one video.

        Args:
            video_segments (list): List of dicts, each with keys:
                - 'path': path to video file
                - 'last_frame': last frame index with people detected (inclusive)
            storage_mode (str): 'local_storage' or 'cloud_storage'

        Returns:
            str: Path to the concatenated video.

        """
        writer = None
        first_segment = str(video_segments[0]["name"])
        output_name = first_segment.replace("CAPTURED", "FILTERED")
        output_path = f"{PhotosFileAdapter().get_filter_folder_path()}/{output_name}"

        for segment in video_segments:
            cap = cv2.VideoCapture(segment["url"])
            try:
                if not cap.isOpened():
                    information = f"Error opening video file: {segment['url']}"
                    raise ValueError(information)

                # Get video properties
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                fourcc = cv2.VideoWriter.fourcc(*"mp4v")

                # Initialize writer if not already done
                if writer is None:
                    writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

                for _ in range(segment["crossings"]["last_frame"] + 1):
                    ret, frame = cap.read()
                    if not ret:
                        break
                    writer.write(frame)
            finally:
                cap.release()
            if writer is not None:
                writer.release()

        # archive the input videos
        for segment in video_segments:
            if storage_mode == "cloud_storage":
                new_blob_name = segment["name"].replace("CAPTURE/CAPTURED_", "CAPTURE/ARCHIVE/CAPTURED_")
                GoogleCloudStorageAdapter().move_blob(segment["name"], new_blob_name)
            elif storage_mode == "local_storage":
                PhotosFileAdapter().move_to_capture_archive(Path(segment["name"]).name)

    async def _list_captured_videos(self, storage_mode: str) -> list:
        """Return a list of name and URLs to captured files."""
        if storage_mode == "cloud_storage":
            return GoogleCloudStorageAdapter().list_blobs("CAPTURE/CAPTURED_")
        if storage_mode == "local_storage":
            return PhotosFileAdapter().get_all_capture_files()
        return []

    async def _process_single_video(
        self,
        model: YOLO,
        video: dict,
        token: str,
        event: dict,
        frame_count: int,
        image_size: tuple,
    ) -> dict:
        """Process a single video stream and return the crossings summary.

        Mirrors the previous inline logic from `filter_video`.
        Raises VideoStreamNotFoundError on model track errors.
        """
        try:
            results = model.track(
                source=video["url"],
                conf=MIN_CONFIDENCE,
                classes=DETECTION_CLASSES,
                stream=True,
                imgsz=image_size,
                persist=True,
            )
        except Exception as e:
            informasjon = f"Error opening video stream from: {video['url']}"
            logging.exception(informasjon)
            raise VideoStreamNotFoundError(informasjon) from e

        trigger_line_xyxyn = await VisionAIService().get_trigger_line_xyxy_list(token, event)
        all_crossings = []
        for result in results:
            frame_count += 1
            all_crossings.append(self.get_all_crossings(frame_count, result, trigger_line_xyxyn))

        return {
            "name": video["name"],
            "url": video["url"],
            "crossings": self.get_crossings_summary(all_crossings)
        }


    def filter_crossings(self, crossings: list) -> list:
        """Filter out persons whose average speed is less than 10% of the overall average speed.

        Args:
            crossings (list): List of frame dicts, each with 'details' containing person info.

        Returns:
            list: Filtered crossings list.

        """
        # Get movement summary
        person_summary = self.summarize_person_movement(crossings)
        avg_speed = person_summary["avg_speed"]
        detail_dict = person_summary["detail_dict"]

        # Calculate speed threshold (10% of average)
        speed_threshold = 0.1 * avg_speed if avg_speed > 0 else 0

        # Build a set of person IDs to keep
        keep_ids = {pid for pid, d in detail_dict.items() if d["avg_speed"] >= speed_threshold}

        # Filter each frame's details
        filtered_crossings = []
        for frame in crossings:
            filtered_details = [d for d in frame["details"] if d["id"] in keep_ids]
            filtered_frame = frame.copy()
            filtered_frame["details"] = filtered_details
            filtered_frame["persons_count"] = len(filtered_details)
            filtered_crossings.append(filtered_frame)

        return filtered_crossings

    def summarize_person_movement(self, frames: list) -> dict:
        """Summarize detected persons: count frames visible and estimate average speed.

        Args:
            frames (list): List of frame dicts as described.

        Returns:
            dict: {person_id: {"frames_visible": int, "avg_speed": float}}

        """
        person_summary = {
            "avg_speed": 0.0,
            "persons_count": 0,
            "detail_dict": {},
        }
        _tmp_speed = 0.0

        person_tracks = defaultdict(list)

        # Collect all positions for each person
        for frame in frames:
            frame_id = frame["frame_id"]
            for detail in frame["details"]:
                pid = detail["id"]
                center = detail["center"]
                person_tracks[pid].append((frame_id, center))

        summary = {}
        for pid, _track in person_tracks.items():
            track = sorted(_track)  # sort by frame_id
            frames_visible = len(track)
            # Calculate total distance and total frames
            total_dist = 0.0
            total_frames = 0
            for i in range(1, len(track)):
                prev_frame, prev_center = track[i-1]
                curr_frame, curr_center = track[i]
                # Euclidean distance in normalized coordinates
                dist = math.sqrt(
                    (curr_center[0] - prev_center[0]) ** 2 +
                    (curr_center[1] - prev_center[1]) ** 2
                )
                frame_gap = curr_frame - prev_frame
                if frame_gap > 0:
                    total_dist += dist
                    total_frames += frame_gap
            avg_speed = (total_dist / total_frames) if total_frames > 0 else 0.0
            summary[pid] = {
                "frames_visible": frames_visible,
                "avg_speed": avg_speed
            }
            person_summary["persons_count"] += 1
            _tmp_speed += avg_speed
            person_summary["detail_dict"] = summary

        person_summary["avg_speed"] = (
            _tmp_speed / person_summary["persons_count"]
            if person_summary["persons_count"] > 0
            else 0.0
        )

        return person_summary

    def get_all_crossings(self, frame_id: int, result: Results, trigger_line: list) -> dict:
        """Analyze result from video analytics to determine crossings."""
        crossings = {
            "frame_id": frame_id,
            "persons_count": 0,
            "details": []
            }
        boxes = result.boxes
        if boxes:
            class_values = boxes.cls

            for y in range(len(class_values)):
                try:

                    d_id = int(boxes.id[y].item())  # type: ignore[attr-defined]
                    xyxyn = boxes.xyxyn[y]
                    # identify person - validation
                    if (
                        (class_values[y] == 0)
                        and (boxes.conf[y].item() > MIN_CONFIDENCE)
                        and VisionAIService().validate_box(xyxyn)
                    ):
                        crossed_line = VisionAIService().is_below_line(
                            xyxyn, trigger_line
                        )
                        if crossed_line != "false":
                            _crossing_details = {
                                "id": d_id,
                                "center": self.get_box_center(xyxyn),
                                "crossed_line": crossed_line,
                            }
                            crossings["details"].append(_crossing_details)
                            crossings["persons_count"] += 1
                except TypeError as e:
                    logging.debug(f"TypeError: {e}")
                    # ignore
        return crossings


    def get_box_center(self, xyxyn: Tensor) -> tuple[float, float]:
        """Get the center (x, y) coordinates of a bounding box in normalized YOLO format.

        Args:
            xyxyn (Tensor): Bounding box in [x1, y1, x2, y2] normalized format.

        Returns:
            tuple: (x_center, y_center) in normalized coordinates (0.0 - 1.0)

        """
        x1, y1, x2, y2 = xyxyn.tolist()
        x_center = (x1 + x2) / 2
        y_center = (y1 + y2) / 2
        return x_center, y_center

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

        # Load an official or custom model
        model = YOLO("yolov8n.pt")  # Load an official Detect model

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

        i_count = 0
        for result in results:
            i_count += VisionAIService().process_boxes(result, trigger_line, crossings, camera_location)

        await ConfigAdapter().update_config(
            token, event["id"], "DETECT_VIDEO_SERVICE_RUNNING", "false"
        )
        informasjon = f"Analytics: {i_count} detections. {informasjon}"
        await StatusAdapter().create_status(
            token, event, "VIDEO_ANALYTICS", informasjon
        )
        return informasjon

