"""Module for status adapter."""

import datetime
import json
import logging
import re

import cv2
import numpy as np
import piexif
from torch import Tensor
from ultralytics.engine.results import Results

from video_service.adapters import (
    ConfigAdapter,
    PhotosFileAdapter,
    StatusAdapter,
    VideoStreamNotFoundError,
)

COUNT_COORDINATES = 4
DETECTION_BOX_MINIMUM_SIZE = 0.08
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
        crop_file_name = f"{file_name}_crop.jpg"
        cv2.imwrite(crop_file_name, combined_image)

    def get_image_info(self, camera_location: str, time_text: str) -> bytes:
        """Create image info EXIF data."""
        # set the params
        image_info = {"passeringspunkt": camera_location, "passeringstid": time_text}

        # create the EXIF data and convert to bytes
        exif_dict = {"0th": {piexif.ImageIFD.ImageDescription: json.dumps(image_info)}}
        return piexif.dump(exif_dict)

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

    def process_boxes(self, result: Results, trigger_line: list, crossings: dict, camera_location: str) -> int:
        """Process result from video analytics."""
        i_count = 0
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
                        box_validation = self.validate_box(xyxyn)
                        if (crossed_line != "false") and box_validation:
                            # Extract screenshot image from the results
                            xyxy = boxes.xyxy[y]
                            if crossed_line != "100":
                                if d_id not in crossings[crossed_line]:
                                    crossings[crossed_line][d_id] = (
                                        VisionAIService().get_crop_image(result.orig_img, xyxy)
                                    )
                            elif d_id not in crossings[crossed_line]:
                                crossings[crossed_line].append(d_id)
                                VisionAIService().save_image(
                                    result,
                                    camera_location,
                                    d_id,
                                    crossings,
                                    xyxy,
                                )
                                i_count += 1

                except TypeError as e:
                    logging.debug(f"TypeError: {e}")
        return i_count

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


    def save_image(
        self,
        result: Results,
        camera_location: str,
        d_id: int,
        crossings: dict,
        xyxy: Tensor,
    ) -> None:
        """Save image and crop_images to file."""
        logging.info(f"Line crossing! ID:{d_id}")
        taken_time = extract_datetime_from_filename(result.path)
        time_text = taken_time.strftime("%Y%m%d %H:%M:%S")

        # save image to file - full size
        timestamp = taken_time.strftime("%Y%m%d_%H%M%S")
        photos_file_path = PhotosFileAdapter().get_video_folder_path("DETECT")
        file_name = f"{photos_file_path}/{camera_location}_{timestamp}_{d_id}.jpg"
        cv2.imwrite(f"{file_name}", result.orig_img)

        # Now insert the EXIF data using piexif
        try:
            exif_bytes = VisionAIService().get_image_info(camera_location, time_text)
            piexif.insert(exif_bytes, file_name)
        except Exception as e:
            informasjon = f"vision_ai_service - Error inserting EXIF: {e}"
            logging.exception(informasjon)

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
            crop_im_list,
            file_name,
        )

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
            photos_file_path = PhotosFileAdapter().get_video_folder_path("")
            file_name = f"{photos_file_path}/{time_text}_{trigger_line_config_file}"
            cv2.imwrite(file_name, cv2.cvtColor(im_rgb, cv2.COLOR_RGB2BGR))  # Convert back to BGR for saving
            informasjon = f"Trigger line <a title={file_name}>photo</a> created."
            await StatusAdapter().create_status(token, event, status_type, informasjon)
            await ConfigAdapter().update_config(
                token, event["id"], "NEW_TRIGGER_LINE_PHOTO", "False"
            )

        except TypeError as e:
            logging.debug(f"TypeError: {e}")
            # ignore

def extract_datetime_from_filename(filename: str) -> datetime.datetime:
    """Extract a datetime object from a file path with pattern YYYYMMDD and HHMMSS."""
    match = re.search(r"(\d{8}_\d{6})", filename)
    if match:
        date_str = match.group(1)
        try:
            return datetime.datetime.strptime(date_str, "%Y%m%d_%H%M%S").astimezone()
        except ValueError:
            logging.exception(f"Invalid date format in filename: {filename}")
    return datetime.datetime.now(datetime.UTC)
