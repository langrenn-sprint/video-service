"""Module adapter for photos on file storage."""

import logging
from pathlib import Path

import cv2

from .config_adapter import ConfigAdapter

VISION_ROOT_PATH = f"{Path.cwd()}/video_service/files"
PHOTOS_FILE_PATH = f"{VISION_ROOT_PATH}/photos"
PHOTOS_ARCHIVE_PATH = f"{PHOTOS_FILE_PATH}/archive"
PHOTOS_URL_PATH = "files/photos"


class PhotosFileAdapter:
    """Class representing photos."""

    def get_photos_folder_path(self) -> str:
        """Get path to photo folder."""
        if not Path(PHOTOS_FILE_PATH).exists():
            try:
                Path(PHOTOS_FILE_PATH).mkdir(parents=True, exist_ok=True)
            except Exception:
                logging.exception(f"Error creating folder: {PHOTOS_FILE_PATH}")
        # Return the path to the photos folder
        return PHOTOS_FILE_PATH

    def init_video_folder(self, mode: str) -> None:
        """Ensure folders exists."""
        my_folder = Path(f"{VISION_ROOT_PATH}/{mode}")
        if not my_folder.exists():
            my_folder.mkdir(parents=True, exist_ok=True)

    def get_video_folder_path(self, mode: str) -> str:
        """Get path to video folder."""
        my_folder = Path(f"{VISION_ROOT_PATH}/{mode}")
        if not my_folder.exists():
            my_folder.mkdir(parents=True, exist_ok=True)
        return f"{VISION_ROOT_PATH}/{mode}"

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
        except FileNotFoundError:
            Path(PHOTOS_FILE_PATH).mkdir(parents=True, exist_ok=True)
        except Exception:
            logging.exception("Error getting photos")
        return photos

    def get_all_files(self, subfolder: str) -> list:
        """Get all url to all files on file directory, sorted by name."""
        my_files = []
        file_directory = f"{VISION_ROOT_PATH}/{subfolder}"
        try:
            my_files = [f for f in Path(file_directory).iterdir() if f.is_file()]
            my_files.sort(key=lambda x: x.name)
        except FileNotFoundError:
            Path(file_directory).mkdir(parents=True, exist_ok=True)
        except Exception:
            informasjon = f"Error getting files, subfolder: {subfolder}"
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
                    self.move_to_archive("photos", f.name)

        except Exception:
            logging.exception("Error getting photos")
        return f"{PHOTOS_URL_PATH}/{trigger_line_file_name}"

    def concatenate_video_segments(self, video_segments: list) -> str:
        """Concatenate segments from multiple videos into one video.

        Args:
            video_segments (list): List of dicts, each with keys:
                - 'path': path to video file
                - 'last_frame': last frame index with people detected (inclusive)

        Returns:
            str: Path to the concatenated video.

        """
        writer = None
        first_segment = str(video_segments[0]["path"])
        output_path = f"FILTERED_{first_segment}"

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

                for _frame_idx in range(segment["last_frame"] + 1):
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
            self.move_to_archive("CAPTURE", Path(segment["path"]).name)
        return output_path

    def move_to_archive(self, subfolder: str, filename: str) -> None:
        """Move photo to archive."""
        source_file = Path(VISION_ROOT_PATH) / subfolder / filename
        archive_folder = Path(VISION_ROOT_PATH) / subfolder / "archive"
        destination_file = Path(archive_folder) / filename

        try:
            source_file.rename(destination_file)
        except FileNotFoundError:
            logging.info("Destination folder not found. Creating...")
            Path(archive_folder).mkdir(parents=True, exist_ok=True)
            source_file.rename(destination_file)
        except Exception:
            logging.exception("Error moving photo to archive.")
