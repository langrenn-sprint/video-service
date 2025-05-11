"""Module for video services."""

import datetime
import logging

import cv2

from video_service.adapters import (
    ConfigAdapter,
    StatusAdapter,
    VideoStreamNotFoundError,
)


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
        informasjon = ""
        video_stream_url = await ConfigAdapter().get_config(token, event["id"], "VIDEO_URL")
        await StatusAdapter().create_status(
            token,
            event,
            status_type,
            f"Starter video capture av <a href={video_stream_url}>video</a>.",
        )
        await ConfigAdapter().update_config(
            token, event["id"], "VIDEO_SERVICE_START", "False"
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
                clip_filename = f"{photos_file_path}/clip_{timestamp}_{clip_count}.avi"
                clip_count += 1

                # Define the codec and create a VideoWriter object
                fourcc = cv2.VideoWriter.fourcc(*"XVID")
                out = cv2.VideoWriter(clip_filename, fourcc, frame_rate, image_size)

                for frame in clip_frames:
                    out.write(frame)
                out.release()

                stop_tracking = await ConfigAdapter().get_config_bool(
                    token, event["id"], "VIDEO_SERVICE_STOP"
                )
                if stop_tracking:
                    await ConfigAdapter().update_config(
                        token, event["id"], "VIDEO_SERVICE_STOP", "False"
                    )
                    break  # No more frames to process

        finally:
            video_capture.release()
            await ConfigAdapter().update_config(
                token, event["id"], "VIDEO_SERVICE_RUNNING", "False"
            )

        # Update status and return result
        await StatusAdapter().create_status(
            token,
            event,
            status_type,
            f"Video capture completed. {clip_count} clips saved.",
        )
        return f"Video capture completed. {clip_count} clips saved."
