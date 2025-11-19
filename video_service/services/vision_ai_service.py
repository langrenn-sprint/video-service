"""Module for status adapter."""

import datetime
import logging
import re

import cv2
import numpy as np
from torch import Tensor
from ultralytics.engine.results import Results

from video_service.adapters import (
    ConfigAdapter,
    StatusAdapter,
    VideoStreamNotFoundError,
)
from video_service.adapters.google_cloud_storage_adapter import (
    GoogleCloudStorageAdapter,
)

COUNT_COORDINATES = 4
DETECTION_BOX_MINIMUM_SIZE = 0.01
DETECTION_BOX_MAXIMUM_SIZE = 0.9
EDGE_MARGIN = 0.02


class VisionAIService:
    """Class representing vision ai services."""

    def get_crop_image(self, im: np.ndarray, xyxy: Tensor) -> np.ndarray:
        """Get cropped image."""
        x1, y1, x2, y2 = map(int, xyxy.tolist())  # Ensure integer coordinates
        return im[y1:y2, x1:x2]  # Cropping in OpenCV (NumPy array slicing)

    def save_crop_images(
        self,
        event_id: str,
        image_list: list[np.ndarray],
        file_name: str,
    ) -> None:
        """Save all crop images in one image file."""
        # OpenCV uses NumPy arrays, so concatenate horizontally
        max_height = max(img.shape[0] for img in image_list)
        padded_images = []
        for img in image_list:
            height_diff = max_height - img.shape[0]
            top = height_diff // 2  # Integer division for even distribution
            bottom = height_diff - top  # Handle odd differences
            left = right = 0
            padded_img = cv2.copyMakeBorder(
                img,
                top,
                bottom,
                left,
                right,
                cv2.BORDER_CONSTANT,
                value=[255, 255, 255]
            )
            padded_images.append(padded_img)

        combined_image = np.concatenate(padded_images, axis=1)

        # Save the original image to Google Cloud Storage
        success, encoded_image = cv2.imencode(".jpg", combined_image)
        if not success:
            information = "Failed to encode crop image for upload."
            raise Exception(information)
        url = GoogleCloudStorageAdapter().upload_blob_bytes(event_id, "DETECT", f"{file_name}_crop.jpg", encoded_image.tobytes(), "image/jpeg", {})
        logging.info(f"Image uploaded to: {url}")

    def create_image_info(self, camera_location: str, time_text: str, box_confidence: float, frame_number: int, video_file_name: str) -> dict:
        """Create image info EXIF data."""
        # set the params
        return {
            "passeringspunkt": camera_location,
            "passeringstid": time_text,
            "sannsynlighet": box_confidence,
            "source_video": video_file_name,
            "sekvensnummer": frame_number
        }

    async def get_trigger_line_xyxy_list(self, token: str, event: dict) -> list:
        """Get list of trigger line coordinates."""
        trigger_line_xyxy = await ConfigAdapter().get_config(
            token, event["id"], "TRIGGER_LINE_XYXYN"
        )
        trigger_line_xyxy_list = []

        try:
            trigger_line_xyxy_list = [float(i) for i in trigger_line_xyxy.split(":")]
        except Exception as e:
            informasjon  = f"Error reading TRIGGER_LINE_XYXYN: {e}"
            logging.exception(informasjon)
            raise Exception(informasjon) from e

        # validate for correct number of coordinates
        if len(trigger_line_xyxy_list) != COUNT_COORDINATES:
            informasjon = "TRIGGER_LINE_XYXYN must have 4 numbers, colon-separated."
            logging.error(informasjon)
            raise Exception(informasjon)
        return trigger_line_xyxy_list

    def process_boxes(self, event_id: str, result: Results, trigger_line: list, crossings: dict, camera_location: str, frame_number: int, min_confidence: float) -> list:
        """Process result from video analytics."""
        detect_url_list = []
        boxes = result.boxes
        if boxes:
            class_values = boxes.cls

            for y in range(len(class_values)):
                try:

                    d_id = int(boxes.id[y].item())  # type: ignore[attr-defined]
                    # identify person - class value 0
                    if (class_values[y] == 0):
                        xyxyn = boxes.xyxyn[y]
                        crossed_line = self.is_below_line(
                            xyxyn, trigger_line
                        )
                        # ignore small boxes
                        box_confidence = self.validate_box(xyxyn)
                        if (crossed_line != "false") and box_confidence > min_confidence:
                            # Extract screenshot image from the results
                            xyxy = boxes.xyxy[y]
                            if crossed_line != "100":
                                if d_id not in crossings[crossed_line]:
                                    crossings[crossed_line][d_id] = (
                                        VisionAIService().get_crop_image(result.orig_img, xyxy)
                                    )
                            elif d_id not in crossings[crossed_line]:
                                crossings[crossed_line].append(d_id)
                                url = VisionAIService().save_detect_image(
                                    event_id,
                                    result,
                                    camera_location,
                                    d_id,
                                    crossings,
                                    xyxy,
                                    frame_number,
                                    box_confidence,
                                )
                                detect_url_list.append(url)

                except TypeError as e:
                    logging.debug(f"TypeError: {e}")
        return detect_url_list

    def validate_box(self, xyxyn: Tensor) -> float:
        """Return probability of valid box from 1 to 0."""
        box_validation = 1.0
        box_with = xyxyn.tolist()[2] - xyxyn.tolist()[0]
        box_heigth = xyxyn.tolist()[3] - xyxyn.tolist()[1]

        # check if box is too small or too big
        if (box_with < DETECTION_BOX_MINIMUM_SIZE) or (box_heigth < DETECTION_BOX_MINIMUM_SIZE):
            return 0.0
        if (box_with > DETECTION_BOX_MAXIMUM_SIZE) or (box_heigth > DETECTION_BOX_MAXIMUM_SIZE):
            return 0.0

        # check if box is at the edge
        if (xyxyn.tolist()[0] < EDGE_MARGIN) or (xyxyn.tolist()[1] < EDGE_MARGIN):
            return 0.75
        if (xyxyn.tolist()[2] > (1 - EDGE_MARGIN)) or (xyxyn.tolist()[3] > (1 - EDGE_MARGIN)):
            return 0.75


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


    def save_detect_image(
        self,
        event_id: str,
        result: Results,
        camera_location: str,
        d_id: int,
        crossings: dict,
        xyxy: Tensor,
        frame_number: int,
        box_confidence: float
    ) -> str:
        """Save image and crop_images to file."""
        logging.info(f"Line crossing! ID:{d_id}")
        taken_time = extract_datetime_from_filename(result.path, frame_number, result.fps)
        time_text = taken_time.strftime("%Y%m%d %H:%M:%S")

        # save image to file - full size
        timestamp = taken_time.strftime("%Y%m%d_%H%M%S")
        file_name = f"{camera_location}_{timestamp}_{frame_number}_{d_id}"
        metadata = VisionAIService().create_image_info(camera_location, time_text, box_confidence, frame_number, result.path)

        # Save the original image to Google Cloud Storage
        success, encoded_image = cv2.imencode(".jpg", result.orig_img)
        if not success:
            information = "Failed to encode image for upload."
            raise Exception(information)
        url = GoogleCloudStorageAdapter().upload_blob_bytes(event_id, "DETECT", f"{file_name}.jpg", encoded_image.tobytes(), "image/jpeg", metadata)
        logging.debug(f"Image uploaded to: {url}")

        # save crop images
        crop_im_list = []
        if d_id in crossings["80"]:
            crop_im_list.append(crossings["80"][d_id])
            crossings["80"].pop(d_id)
        if d_id in crossings["90"]:
            crop_im_list.append(crossings["90"][d_id])
            crossings["90"].pop(d_id)
        # add crop of saved image (100)
        crop_im_list.append(VisionAIService().get_crop_image(result.orig_img, xyxy))

        VisionAIService().save_crop_images(
            event_id,
            crop_im_list,
            file_name,
        )
        return url

    async def print_photo_with_trigger_line(
        self,
        token: str,
        event: dict,
        status_type: str,
    ) -> None:
        """Print an image with a trigger line."""
        trigger_line_xyxyn = await self.get_trigger_line_xyxy_list(
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
            _, im = cap.read()
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
            font_scale = 2
            font_color = (255, 0, 0)  # red

            # get the current time with timezone
            current_time = datetime.datetime.now(datetime.UTC)
            time_text = current_time.strftime("%Y%m%d_%H%M%S")
            image_time_text = (
                f"Line coordinates: {trigger_line_xyxyn}. Time: {time_text}"
            )
            cv2.putText(im_rgb, image_time_text, (50, 50), font_face, font_scale, font_color, 2, cv2.LINE_AA)

            # save image to file
            file_name = f"{time_text}_trigger_line.jpg"

            # Save the original image to Google Cloud Storage
            success, encoded_image = cv2.imencode(".jpg", cv2.cvtColor(im_rgb, cv2.COLOR_RGB2BGR))
            if not success:
                information = "Failed to encode image for upload."
                raise Exception(information)
            url = GoogleCloudStorageAdapter().upload_blob_bytes(event["id"], "TRIGGER_LINE", file_name, encoded_image.tobytes(), "image/jpeg", {})
            logging.info(f"Image uploaded to: {url}")

            informasjon = f"Trigger line <a title={file_name}>photo</a> created."
            await StatusAdapter().create_status(token, event, status_type, informasjon)
            await ConfigAdapter().update_config(
                token, event["id"], "NEW_TRIGGER_LINE_PHOTO", "False"
            )
            await ConfigAdapter().update_config(
                token, event["id"], "TRIGGER_LINE_PHOTO_URL", url
            )

        except TypeError as e:
            logging.debug(f"TypeError: {e}")
            # ignore

def extract_datetime_from_filename(filename: str, frame_number: int, fps: int) -> datetime.datetime:
    """Extract a datetime object from a file path with pattern YYYYMMDD and HHMMSS."""
    match = re.search(r"(\d{8}_\d{6})", filename)
    if match:
        date_str = match.group(1)
        try:
            taken_time = datetime.datetime.strptime(date_str, "%Y%m%d_%H%M%S").astimezone()
            return taken_time + datetime.timedelta(seconds=frame_number // fps)
        except ValueError:
            logging.exception(f"Invalid date format in filename: {filename}")
    return datetime.datetime.now(datetime.UTC)
