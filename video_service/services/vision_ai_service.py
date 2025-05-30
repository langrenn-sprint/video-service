"""Module for status adapter."""

import datetime
import json
import logging

import cv2
import numpy as np
import piexif
from torch import Tensor
from ultralytics.engine.results import Results

from video_service.adapters import (
    ConfigAdapter,
    StatusAdapter,
)

COUNT_COORDINATES = 4


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

    async def check_stop_tracking(
        self, token: str, event: dict, status_type: str
    ) -> bool:
        """Check status flags and determine if tracking should continue."""
        stop_tracking = await ConfigAdapter().get_config_bool(
            token, event["id"], "VIDEO_ANALYTICS_STOP"
        )
        if stop_tracking:
            await StatusAdapter().create_status(
                token, event, status_type, "Video analytics stopped."
            )
            await ConfigAdapter().update_config(
                token, event["id"], "VIDEO_ANALYTICS_RUNNING", "False"
            )
            await ConfigAdapter().update_config(
                token, event["id"], "VIDEO_ANALYTICS_STOP", "False"
            )
            return True
        return False

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

    def save_image(
        self,
        result: Results,
        camera_location: str,
        photos_file_path: str,
        d_id: int,
        crossings: dict,
        xyxy: Tensor,
    ) -> None:
        """Save image and crop_images to file."""
        logging.info(f"Line crossing! ID:{d_id} {photos_file_path}")
        current_time = datetime.datetime.now(datetime.UTC)
        time_text = current_time.strftime("%Y%m%d %H:%M:%S")

        # save image to file - full size
        timestamp = current_time.strftime("%Y%m%d_%H%M%S")
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
