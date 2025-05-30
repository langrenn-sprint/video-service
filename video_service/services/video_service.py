"""Module for video services."""

import datetime
import logging

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
DETECTION_BOX_MINIMUM_SIZE = 0.08
DETECTION_BOX_MAXIMUM_SIZE = 0.9
EDGE_MARGIN = 0.02
MIN_CONFIDENCE = 0.6
DETECTION_CLASSES = [0]  # person

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
        await StatusAdapter().create_status(
            token,
            event,
            status_type,
            f"Starter video capture av <a href={video_stream_url}>video</a>.",
        )
        await ConfigAdapter().update_config(
            token, event["id"], f"{mode}_VIDEO_SERVICE_START", "False"
        )

        # Define the desired image size as a tuple (width, height)
        image_size = await ConfigAdapter().get_config_img_res_tuple(
            token, event["id"], "VIDEO_ANALYTICS_IMAGE_SIZE"
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

        frame_rate = int(video_capture.get(cv2.CAP_PROP_FPS))  # Get the frame rate of the video
        frames_per_clip = frame_rate * clip_duration  # Calculate the number of frames for a 15-second clip
        clip_count = 0

        try:
            while True:
                clip_frames = []
                for _ in range(frames_per_clip):
                    ret, frame = video_capture.read()
                    if not ret:
                        break  # End of video stream

                    # Resize frame to the desired image size
                    resized_frame = cv2.resize(frame, image_size)
                    clip_frames.append(resized_frame)

                if not clip_frames:
                    break  # No more frames to process

                # Save the clip to a file
                timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%S")
                clip_filename = f"{photos_file_path}/{mode}_{timestamp}_{clip_count}{VIDEO_SUFFIX}"
                clip_count += 1

                # Define the codec and create a VideoWriter object
                fourcc = cv2.VideoWriter.fourcc(*"XVID")
                out = cv2.VideoWriter(clip_filename, fourcc, frame_rate, image_size)

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
        clip_count = 0
        informasjon = ""
        await ConfigAdapter().update_config(
            token, event["id"], "ENHANCE_VIDEO_SERVICE_START", "False"
        )


        # Open the video stream for captured video clips
        video_urls = PhotosFileAdapter().get_all_files("CAPTURE", VIDEO_SUFFIX)
        if video_urls:
            await ConfigAdapter().update_config(
                token, event["id"], "VIDEO_ANALYTICS_RUNNING", "True"
            )
        model = YOLO("yolov8n.pt")  # Load an official Detect model
        image_size = (640, 480) # Set low image size for faster processing
        video_stream_detections = {}
        for video_stream_url in video_urls:

            # Perform tracking with the model
            clip_count += 1
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
                logging.info(f"Processing video: {video_stream_url}")
                all_crossings.append(
                    self.get_all_crossings(result, trigger_line_xyxyn)
                )
            # analyse results and identify crossings in the video stream
            crossings_summary = self.get_crossings_summary(all_crossings)
            video_stream_detections[video_stream_url] = crossings_summary

        # Save the relevant clips to a new video file
        segments = []
        output_path = ""
        for video_stream_url, crossings_summary in video_stream_detections.items():
            crossings_summary["path"] = video_stream_url
            segments.append(crossings_summary)
        output_path = segments[0]["path"].replace("CAPTURE", "ENHANCE")
        PhotosFileAdapter().concatenate_video_segments(segments, output_path)


        # Update status and return result
        await ConfigAdapter().update_config(
            token, event["id"], f"{mode}_VIDEO_SERVICE_RUNNING", "False"
        )
        await StatusAdapter().create_status(
            token,
            event,
            status_type,
            f"Video capture completed. {clip_count} clips saved.",
        )
        return f"Video capture completed. {clip_count} clips saved."

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
        for crossing in crossings:
            i_count += 1
            persons = sum(
                len(crossing[key]) for key in crossing if key in ["100", "90", "80"]
            )
            crossings_summary["max_persons"] = max(crossings_summary["max_persons"], persons)
            crossings_summary["min_persons"] = min(crossings_summary["min_persons"], persons)
            if persons > 0:
                if i_first_detection == 0:
                    i_first_detection = i_count
                i_last_detection = i_count
        crossings_summary["first_frame"] = i_first_detection - 1
        crossings_summary["last_frame"] = i_last_detection
        crossings_summary["total_frames"] = i_count
        return crossings_summary

    def get_all_crossings(self, result: Results, trigger_line: list) -> dict:
        """Analyze result from video analytics to determine crossings."""
        crossings = {
            "100": [],
            "90": [],
            "80": [],
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
                        and self.validate_box(xyxyn)
                    ):
                        crossed_line = self.is_below_line(
                            xyxyn, trigger_line
                        )
                        if crossed_line != "false":
                            if d_id not in crossings[crossed_line]:
                                crossings[crossed_line].append(d_id)
                except TypeError as e:
                    logging.debug(f"TypeError: {e}")
                    # ignore
        return crossings


    def validate_box(self, xyxyn: Tensor) -> bool:
        """Filter out boxes not relevant."""
        box_validation = True
        box_with = xyxyn.tolist()[2] - xyxyn.tolist()[0]
        box_heigth = xyxyn.tolist()[3] - xyxyn.tolist()[1]

        # check if box is too small and at the edge
        if (box_with < DETECTION_BOX_MINIMUM_SIZE) or (box_heigth < DETECTION_BOX_MINIMUM_SIZE):
            if (xyxyn.tolist()[2] > (1 - EDGE_MARGIN)) or (xyxyn.tolist()[3] > (1 - EDGE_MARGIN)):
                return False

        if (box_with > DETECTION_BOX_MAXIMUM_SIZE) or (box_heigth > DETECTION_BOX_MAXIMUM_SIZE):
            return False

        return box_validation

    def is_below_line(self, xyxyn: Tensor, trigger_line: list) -> str:
        """Check if a point is below a trigger line."""
        x_center_pos = (xyxyn.tolist()[2] + xyxyn.tolist()[0]) / 2
        y_lower_pos = xyxyn.tolist()[3]
        x1 = trigger_line[0]
        y1 = trigger_line[1]
        x2 = trigger_line[2]
        y2 = trigger_line[3]
        # check if more than half of the box is outside line x values
        if (x_center_pos < x1) or (x_center_pos > x2):
            return "false"
        # get line derivated
        a = (y2 - y1) / (x2 - x1)
        # get line y value at point x and check if point y is below
        y = a * (x_center_pos - x1) + y1
        y_80 = a * (x_center_pos - x1) + (y1 * 0.8)
        y_90 = a * (x_center_pos - x1) + (y1 * 0.9)
        if y_lower_pos > y:
            return "100"
        if y_lower_pos > y_90:
            return "90"
        if y_lower_pos > y_80:
            return "80"
        return "false"

    async def print_image_with_trigger_line_v2(
        self,
        token: str,
        event: dict,
        status_type: str,
        photos_file_path: str,
    ) -> None:
        """Print an image with a trigger line."""
        trigger_line_xyxyn = await VisionAIService().get_trigger_line_xyxy_list(
            token, event
        )
        video_stream_url = await ConfigAdapter().get_config(token, event["id"], "VIDEO_URL")

        cap = cv2.VideoCapture(video_stream_url)
        # check if video stream is opened
        if not cap.isOpened():
            informasjon = f"Error opening video stream from: {video_stream_url}"
            logging.error(informasjon)
            raise VideoStreamNotFoundError(informasjon) from None
        try:
            # Show the results
            ret_save, im = cap.read()
            # Convert the frame to RBG
            im_rgb = cv2.cvtColor(im, cv2.COLOR_BGR2RGB)

            # Draw the trigger line
            x1, y1, x2, y2 = map(float, trigger_line_xyxyn)  # Ensure integer coordinates
            cv2.line(
                im_rgb,
                (int(x1 * im.shape[1]), int(y1 * im.shape[0])),
                (int(x2 * im.shape[1]), int(y2 * im.shape[0])),
                (255, 0, 0),  # Color (BGR)
                5
            )  # Thickness

            # Draw the grid lines
            for x in range(10, 100, 10):
                cv2.line(
                    im_rgb,
                    (int(x * im.shape[1] / 100), 0),
                    (int(x * im.shape[1] / 100), im.shape[0]),
                    (255, 255, 255),
                    1
                )
            for y in range(10, 100, 10):
                cv2.line(
                    im_rgb,
                    (0, int(y * im.shape[0] / 100)),
                    (im.shape[1], int(y * im.shape[0] / 100)),
                    (255, 255, 255),
                    1
                )

            # Add text (using OpenCV)
            font_face = 1
            font_scale = 1
            font_color = (255, 0, 0)  # red

            # get the current time with timezone
            current_time = datetime.datetime.now(datetime.UTC)
            time_text = current_time.strftime("%Y%m%d_%H%M%S")
            image_time_text = (
                f"Line coordinates: {trigger_line_xyxyn}. Time: {time_text}"
            )
            cv2.putText(im_rgb, image_time_text, (50, 50), font_face, font_scale, font_color, 2, cv2.LINE_AA)

            # save image to file
            trigger_line_config_file = await ConfigAdapter().get_config(
                token, event["id"], "TRIGGER_LINE_CONFIG_FILE"
            )
            file_name = f"{photos_file_path}/{time_text}_{trigger_line_config_file}"
            cv2.imwrite(file_name, cv2.cvtColor(im_rgb, cv2.COLOR_RGB2BGR))  # Convert back to BGR for saving
            informasjon = f"Trigger line <a title={file_name}>photo</a> created."
            await StatusAdapter().create_status(token, event, status_type, informasjon)

        except TypeError as e:
            logging.debug(f"TypeError: {e}")
            # ignore
