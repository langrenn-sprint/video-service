"""Module for video services."""

import datetime
import logging
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
from video_service.services.vision_ai_service import (
    VisionAIService,
)

VIDEO_SUFFIX = ".avi"
DETECTION_CLASSES = [0]  # person
MAX_CLIPS_TO_CONCATENATE = 10  # maximum number of clips per enhanced video
MIN_CONFIDENCE = 0.6

class VideoService:
    """Class representing video service."""

    async def capture_video(
        self,
        token: str,
        event: dict,
        status_type: str,
        photos_file_path: str,
    ) -> str:
        """Capture video from a stream, save the video to a file, each clip 15 seconsds long.

        The video is saved in the specified directory with a timestamp in the filename.

        Args:
            token: To update databes
            event: Event details
            status_type: To update status messages
            photos_file_path: The path to the directory where the photos will be saved.

        Returns:
            A string indicating the status of the video analytics.

        Raises:
            VideoStreamNotFoundError: If the video stream cannot be found.

        """
        mode = "CAPTURE"
        informasjon = ""
        video_stream_url = await ConfigAdapter().get_config(token, event["id"], "VIDEO_URL")
        video_clip_fps = await ConfigAdapter().get_config_int(token, event["id"], "VIDEO_CLIP_FPS")
        await StatusAdapter().create_status(
            token,
            event,
            status_type,
            f"Starter video capture av <a href={video_stream_url}>video</a>.",
        )
        await ConfigAdapter().update_config(
            token, event["id"], f"{mode}_VIDEO_SERVICE_START", "False"
        )

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
                clip_filename = f"{photos_file_path}/{mode}_{timestamp}_{clip_count}{VIDEO_SUFFIX}"
                clip_count += 1

                # Define the codec and create a VideoWriter object
                fourcc = cv2.VideoWriter.fourcc(*"XVID")
                out = cv2.VideoWriter(clip_filename, fourcc, video_clip_fps, image_size)

                for frame in clip_frames:
                    out.write(frame)
                out.release()

                stop_tracking = await ConfigAdapter().get_config_bool(
                    token, event["id"], f"{mode}_VIDEO_SERVICE_STOP"
                )
                if stop_tracking:
                    await ConfigAdapter().update_config(
                        token, event["id"], f"{mode}_VIDEO_SERVICE_STOP", "False"
                    )
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
            f"Video capture completed. {clip_count} clips saved.",
        )
        return f"Video capture completed. {clip_count} clips saved."


    async def enhance_video(
        self,
        token: str,
        event: dict,
        status_type: str,
    ) -> str:
        """Enhance video from a video clips.

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
        mode = "ENHANCE"
        informasjon = ""
        await ConfigAdapter().update_config(
            token, event["id"], f"{mode}_VIDEO_SERVICE_START", "False"
        )

        while True:
            clip_count = 0
            frame_count = 0

            # Open the video stream for captured video clips
            video_urls = PhotosFileAdapter().get_all_files("CAPTURE", VIDEO_SUFFIX)
            if video_urls:
                await ConfigAdapter().update_config(
                    token, event["id"], f"{mode}_VIDEO_SERVICE_RUNNING", "True"
                )
            model = YOLO("yolov8n.pt")  # Load an official Detect model
            image_size = (640, 480) # Set low image size for faster processing
            video_stream_detections = {}
            for video_stream_url in video_urls:

                # Perform tracking with the model
                clip_count += 1
                if clip_count > MAX_CLIPS_TO_CONCATENATE:
                    break
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

                trigger_line_xyxyn = await VisionAIService().get_trigger_line_xyxy_list(
                    token, event
                )
                all_crossings = []
                for result in results:
                    # get overview of people crossing the trigger line
                    frame_count += 1
                    all_crossings.append(
                        self.get_all_crossings(frame_count, result, trigger_line_xyxyn)
                    )
                # analyse results and identify crossings in the video stream
                crossings_summary = self.get_crossings_summary(all_crossings)
                video_stream_detections[video_stream_url] = crossings_summary

            # Save the relevant clips to a new video file
            segments = []
            output_path = ""
            video_index = 0
            max_clips = await ConfigAdapter().get_config_int(token, event["id"], "MAX_CLIPS_PER_ENHANCED_VIDEO")
            for video_stream_url, crossings_summary in video_stream_detections.items():
                video_index += 1
                crossings_summary["path"] = video_stream_url
                segments.append(crossings_summary)
                if (crossings_summary["last_frame"] < crossings_summary["total_frames"]) or (video_index >= max_clips):
                    output_path = segments[0]["path"].replace("CAPTURE", "ENHANCE")
                    PhotosFileAdapter().concatenate_video_segments(segments, output_path)
                    segments.clear()  # Clear segments for the next video stream
                    video_index = 0

            # Update status and return result
            await ConfigAdapter().update_config(
                token, event["id"], f"{mode}_VIDEO_SERVICE_RUNNING", "False"
            )
            await StatusAdapter().create_status(
                token,
                event,
                status_type,
                f"Video enhance completed. {clip_count} clips saved.",
            )

            check_stop_tracking = await ConfigAdapter().get_config_bool(
                token, event["id"], f"{mode}_VIDEO_SERVICE_STOP"
            )
            if check_stop_tracking:
                await ConfigAdapter().update_config(
                    token, event["id"], f"{mode}_VIDEO_SERVICE_STOP", "False"
                )
                break
        return f"Video enhance completed. {clip_count} clips saved."


    async def detect_crossings(
        self,
        token: str,
        event: dict,
        status_type: str,
    ) -> str:
        """Detect crossing video from enhanced video clips.

        Screenshots with crossings are taken. The video archived.

        Args:
            token: To update databes
            event: Event details
            status_type: To update status messages

        Returns:
            A string indicating the status of the video analytics.

        Raises:
            VideoStreamNotFoundError: If the video stream cannot be found.

        """
        mode = "DETECT"
        await ConfigAdapter().update_config(
            token, event["id"], f"{mode}_VIDEO_SERVICE_START", "False"
        )
        crossings_count = 0

        while True:

            # Open the video stream for enhanced video clips
            video_urls = PhotosFileAdapter().get_all_files("ENHANCE", VIDEO_SUFFIX)
            if video_urls:
                await ConfigAdapter().update_config(
                    token, event["id"], f"{mode}_VIDEO_SERVICE_RUNNING", "True"
                )
            for video_stream_url in video_urls:
                await self.detect_crossings_with_ultraltyics(token, event, video_stream_url)
                PhotosFileAdapter().move_to_archive(Path(video_stream_url).name)


            # Update status and return result
            await ConfigAdapter().update_config(
                token, event["id"], f"{mode}_VIDEO_SERVICE_RUNNING", "False"
            )
            await StatusAdapter().create_status(
                token,
                event,
                status_type,
                f"Crossings detection completed. {crossings_count} crossings saved.",
            )

            check_stop_tracking = await ConfigAdapter().get_config_bool(
                token, event["id"], f"{mode}_VIDEO_SERVICE_STOP"
            )
            if check_stop_tracking:
                await ConfigAdapter().update_config(
                    token, event["id"], f"{mode}_VIDEO_SERVICE_STOP", "False"
                )
                break
        return f"Crossings detection completed. {crossings_count} crossings saved."

    def get_crossings_summary(self, crossings: list) -> dict:
        """Analyze crossings and get overview of frames with relevant information."""
        crossings_summary = {
            "min_persons": 0,
            "max_persons": 0,
            "first_frame": 0,
            "last_frame": 0,
            "total_frames": 0,
        }
        i_count = 0
        i_first_detection = 0
        i_last_detection = 0

        # get overview of persons moving - purpose is to ignore persons that are not moving
        filtered_crossings = self.filter_crossings(crossings)

        for crossing in filtered_crossings:
            i_count += 1
            crossings_summary["max_persons"] = max(crossings_summary["max_persons"], crossing["persons_count"])
            crossings_summary["min_persons"] = min(crossings_summary["min_persons"], crossing["persons_count"])
            if crossing["persons_count"] > 0:
                if i_first_detection == 0:
                    i_first_detection = i_count
                i_last_detection = i_count
        crossings_summary["first_frame"] = i_first_detection - 1
        crossings_summary["last_frame"] = i_last_detection
        crossings_summary["total_frames"] = i_count
        return crossings_summary

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
        import math
        from collections import defaultdict

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
            token, event["id"], "VIDEO_ANALYTICS_IMAGE_SIZE"
        )
        trigger_line = (
            await VisionAIService().get_trigger_line_xyxy_list(
                token, event
            )
        )
        await ConfigAdapter().update_config(
            token, event["id"], "VIDEO_ANALYTICS_RUNNING", "True"
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

        for result in results:
            VisionAIService().process_boxes(result, trigger_line, crossings, camera_location)

        await ConfigAdapter().update_config(
            token, event["id"], "VIDEO_ANALYTICS_RUNNING", "false"
        )

        return f"Analytics completed {informasjon}."

