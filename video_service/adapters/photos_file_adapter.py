"""Module adapter for photos on file storage."""

import logging
from pathlib import Path

import cv2

from .config_adapter import ConfigAdapter

PHOTOS_FILE_PATH = f"{Path.cwd()}/video_service/files"
PHOTOS_ARCHIVE_PATH = f"{PHOTOS_FILE_PATH}/archive"
PHOTOS_URL_PATH = "files"


class PhotosFileAdapter:
    """Class representing photos."""

    def get_photos_folder_path(self) -> str:
        """Get path to photo folder."""
        return PHOTOS_FILE_PATH

    def get_photos_archive_folder_path(self) -> str:
        """Get path to photo archive folder."""
        return PHOTOS_ARCHIVE_PATH

    def get_all_photos(self) -> list:
        """Get all path/filename to all photos on file directory."""
        photos = []
        try:
            files = list(Path(PHOTOS_FILE_PATH).iterdir())
            photos = [
                f"{PHOTOS_FILE_PATH}/{f.name}"
                for f in files
                if f.suffix in [".jpg", ".png"] and "_config" not in f.name
            ]
        except Exception:
            logging.exception("Error getting photos")
        return photos

    def get_all_files(self, prefix: str, suffix: str) -> list:
        """Get all url to all files on file directory with given prefix and suffix."""
        my_files = []
        try:
            files = list(Path(PHOTOS_FILE_PATH).iterdir())  # Materialize iterator and close it
            my_files = [
                f"{PHOTOS_FILE_PATH}/{file.name}"
                for file in files
                if file.suffix == suffix and prefix in file.name
            ]
        except Exception:
            informasjon = f"Error getting files, prefix: {prefix}, suffix: {suffix}"
            logging.exception(informasjon)
        return my_files

    async def get_trigger_line_file_url(self, token: str, event: dict) -> str:
        """Get url to latest trigger line photo."""
        key = "TRIGGER_LINE_CONFIG_FILE"
        file_identifier = await ConfigAdapter().get_config(token, event["id"], key)
        trigger_line_file_name = ""
        try:
            # Lists files in a directory sorted by creation date, newest first."""
            files = list(Path(PHOTOS_FILE_PATH).iterdir())  # Materialize iterator and close it
            files_with_ctime = [
                (f, (Path(PHOTOS_FILE_PATH) / f).stat().st_ctime) for f in files
            ]
            sorted_files = [
                f[0] for f in sorted(files_with_ctime, key=lambda x: x[1], reverse=True)
            ]
            trigger_line_files = [
                f for f in sorted_files if file_identifier in f.name
            ]
            # Return url to newest file, archive
            if len(trigger_line_files) == 0:
                return ""
            trigger_line_file_name = trigger_line_files[0]
            if len(trigger_line_files) > 1:
                for f in trigger_line_files[1:]:
                    self.move_to_archive(f.name)

        except Exception:
            logging.exception("Error getting photos")
        return f"{PHOTOS_URL_PATH}/{trigger_line_file_name}"

    def concatenate_video_segments(self, video_segments: list, output_path: str) -> str:
        """Concatenate segments from multiple videos into one video.

        Args:
            video_segments (list): List of dicts, each with keys:
                - 'path': path to video file
                - 'first_frame': first frame index (inclusive)
                - 'last_frame': last frame index (inclusive)
            output_path (str): Path to save the concatenated video.

        Returns:
            str: Path to the concatenated video.

        """
        writer = None
        for segment in video_segments:
            cap = cv2.VideoCapture(segment["path"])
            try:
                if not cap.isOpened():
                    information = f"Error opening video file: {segment['path']}"
                    raise ValueError(information)

                # Get video properties
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                fourcc = cv2.VideoWriter.fourcc(*"XVID")

                # Initialize writer if not already done
                if writer is None:
                    writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

                # Set to first frame
                cap.set(cv2.CAP_PROP_POS_FRAMES, segment["first_frame"])
                for _frame_idx in range(segment["first_frame"], segment["last_frame"] + 1):
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
            self.move_to_archive(Path(segment["path"]).name)
        return output_path

    def move_to_archive(self, filename: str) -> None:
        """Move photo to archive."""
        source_file = Path(PHOTOS_FILE_PATH) / filename
        destination_file = Path(PHOTOS_ARCHIVE_PATH) / source_file.name

        try:
            source_file.rename(destination_file)
        except FileNotFoundError:
            logging.info("Destination folder not found. Creating...")
            Path(PHOTOS_ARCHIVE_PATH).mkdir(parents=True, exist_ok=True)
            source_file.rename(destination_file)
        except Exception:
            logging.exception("Error moving photo to archive.")
