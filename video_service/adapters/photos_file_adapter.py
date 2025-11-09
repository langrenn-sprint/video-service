"""Module adapter for photos on file storage."""

import logging
import subprocess
from pathlib import Path

from video_service.adapters.google_cloud_storage_adapter import (
    GoogleCloudStorageAdapter,
)

VISION_ROOT_PATH = f"{Path.cwd()}/integration_service/files"
CAPTURED_FILE_PATH = f"{Path.cwd()}/integration_service/files/CAPTURE"
CAPTURED_RAW_FILE_PATH = f"{Path.cwd()}/video_service/files/RAW_CAPTURE/"
CAPTURED_ARCHIVE_PATH = f"{Path.cwd()}/integration_service/files/CAPTURE/archive"
CAPTURED_ERROR_ARCHIVE_PATH = f"{Path.cwd()}/integration_service/files/CAPTURE/error_archive"
PHOTOS_ARCHIVE_PATH = f"{VISION_ROOT_PATH}/archive"
PHOTOS_URL_PATH = "files"


class PhotosFileAdapter:
    """Class representing photos."""

    def get_photos_folder_path(self) -> str:
        """Get path to photo folder."""
        return VISION_ROOT_PATH

    def init_video_folders(self) -> None:
        """Ensure folders exists."""
        my_folder = Path(CAPTURED_FILE_PATH)
        if not my_folder.exists():
            my_folder.mkdir(parents=True, exist_ok=True)
        my_folder = Path(CAPTURED_RAW_FILE_PATH)
        if not my_folder.exists():
            my_folder.mkdir(parents=True, exist_ok=True)

    def get_capture_folder_path(self) -> str:
        """Get path to captured videos folder."""
        return CAPTURED_FILE_PATH

    def get_raw_capture_folder_path(self) -> str:
        """Get path to raw captured video folder."""
        return CAPTURED_RAW_FILE_PATH

    def get_photos_archive_folder_path(self) -> str:
        """Get path to photo archive folder."""
        return PHOTOS_ARCHIVE_PATH

    def get_all_photos(self) -> list:
        """Get all path/filename to all photos on file directory."""
        photos = []
        try:
            files = list(Path(VISION_ROOT_PATH).iterdir())
            photos = [
                f"{VISION_ROOT_PATH}/{f.name}"
                for f in files
                if f.suffix in [".jpg", ".png"] and "_config" not in f.name
            ]
        except Exception:
            logging.exception("Error getting photos")
        return photos

    def get_all_capture_files(self, event_id: str, storage_mode: str) ->  list[dict]:
        """Get all url to all captured files on file directory."""
        file_list = []
        try:
            if storage_mode == "cloud_storage":
                file_list = GoogleCloudStorageAdapter().list_blobs(event_id, "CAPTURE/")
            else:
                # Local file system
                files = list(Path(CAPTURED_FILE_PATH).iterdir())
                file_list = [
                    {"name": f.name, "url": f"{CAPTURED_FILE_PATH}/{f.name}"}
                    for f in files
                if f.is_file()
                ]
        except Exception:
            informasjon = "Error getting captured files"
            logging.exception(informasjon)
            return []
        else:
            return file_list

    def get_all_raw_capture_files(self, event_id: str, storage_mode: str) ->  list[dict]:
        """Get all url to all raw captured files on file directory."""
        file_list = []
        try:
            if storage_mode == "cloud_storage":
                file_list = GoogleCloudStorageAdapter().list_blobs(event_id, "RAW_CAPTURE/")
            else:
                # Local file system
                files = list(Path(CAPTURED_FILE_PATH).iterdir())
                file_list = [
                    {"name": f.name, "url": f"{CAPTURED_RAW_FILE_PATH}/{f.name}"}
                    for f in files
                if f.is_file()
                ]
        except Exception:
            informasjon = "Error getting captured files"
            logging.exception(informasjon)
            return []
        else:
            return file_list

    def get_all_files(self, prefix: str, suffix: str) -> list:
        """Get all url to all files on file directory with given prefix and suffix."""
        my_files = []
        try:
            files = list(Path(VISION_ROOT_PATH).iterdir())  # Materialize iterator and close it
            my_files = [
                f"{VISION_ROOT_PATH}/{file.name}"
                for file in files
                if file.suffix == suffix and prefix in file.name
            ]
        except Exception:
            informasjon = f"Error getting files, prefix: {prefix}, suffix: {suffix}"
            logging.exception(informasjon)
        return my_files

    def move_photo_to_archive(self, filename: str) -> None:
        """Move photo to archive."""
        source_file = Path(VISION_ROOT_PATH) / filename
        destination_file = Path(PHOTOS_ARCHIVE_PATH) / source_file.name

        try:
            source_file.rename(destination_file)
        except FileNotFoundError:
            logging.info("Destination folder not found. Creating...")
            Path(PHOTOS_ARCHIVE_PATH).mkdir(parents=True, exist_ok=True)
            source_file.rename(destination_file)
        except Exception:
            logging.exception("Error moving photo to archive.")


    def move_to_archive(self, filename: str) -> None:
        """Move photo to archive."""
        source_file = Path(VISION_ROOT_PATH) / filename
        destination_file = Path(PHOTOS_ARCHIVE_PATH) / source_file.name

        try:
            source_file.rename(destination_file)
        except FileNotFoundError:
            logging.info("Destination folder not found. Creating...")
            Path(PHOTOS_ARCHIVE_PATH).mkdir(parents=True, exist_ok=True)
            source_file.rename(destination_file)
        except Exception:
            logging.exception("Error moving photo to archive.")

    def move_to_capture_archive(self, event_id: str, storage_mode: str, filename: str) -> str:
        """Move photo to local archive."""
        if storage_mode == "cloud_storage":
            return GoogleCloudStorageAdapter().move_to_capture_archive(
                event_id, filename
            )
        source_file = Path(CAPTURED_FILE_PATH) / filename
        destination_file = Path(CAPTURED_ARCHIVE_PATH) / filename
        try:
            source_file.rename(destination_file)
        except FileNotFoundError:
            logging.info("Destination folder not found. Creating.")
            Path(CAPTURED_ARCHIVE_PATH).mkdir(parents=True, exist_ok=True)
            source_file.rename(destination_file)
        except Exception:
            logging.exception(f"Error moving photo to archive: {filename}")
        return destination_file.name

    def move_to_error_archive(self, event_id: str, storage_mode: str, filename: str) -> str:
        """Move photo to local error archive."""
        if storage_mode == "cloud_storage":
            return GoogleCloudStorageAdapter().move_to_error_archive(
                event_id, filename
            )
        source_file = Path(CAPTURED_FILE_PATH) / filename
        destination_file = Path(CAPTURED_ERROR_ARCHIVE_PATH) / filename
        try:
            source_file.rename(destination_file)
        except FileNotFoundError:
            logging.info("Destination folder not found. Creating.")
            Path(CAPTURED_ERROR_ARCHIVE_PATH).mkdir(parents=True, exist_ok=True)
            source_file.rename(destination_file)
        except Exception:
            logging.exception(f"Error moving photo to error archive: {filename}")
        return destination_file.name

    def convert_raw_to_mp4(self, input_file: str) -> None:
        """Convert (and repair) a video file to MP4 using FFmpeg."""
        # Validate file paths to prevent command injection (S603)
        # Ensure paths are resolved and don't contain shell metacharacters
        try:
            input_path = Path(input_file).resolve()
            output_path = Path(CAPTURED_FILE_PATH) / input_path.name
        except (ValueError, OSError) as e:
            err_msg = f"Invalid file path provided: {e}"
            logging.exception(err_msg)
            raise ValueError(err_msg) from e

        try:
            command = [
                "ffmpeg",
                "-i", str(input_path),
                "-c:v", "libx264",  # H.264 video codec
                "-preset", "fast",  # Encoding speed preset
                "-crf", "23",      # Constant Rate Factor (quality)
                "-c:a", "aac",    # AAC audio codec
                "-b:a", "128k",    # Audio bitrate
                str(output_path)
            ]
            subprocess.run(command, check=True)  # noqa: S603
        except subprocess.CalledProcessError as e:
            informasjon = f"FFmpeg command failed with error for {input_file}"
            logging.exception(informasjon)
            raise Exception(informasjon) from e

