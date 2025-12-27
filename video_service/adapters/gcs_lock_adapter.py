"""Module for google cloud storage adapter."""

import logging
import os
import time

from dotenv import load_dotenv
from google.api_core import exceptions
from google.cloud import storage

load_dotenv()
GOOGLE_STORAGE_BUCKET = os.getenv("GOOGLE_STORAGE_BUCKET")
GOOGLE_STORAGE_SERVER = os.getenv("GOOGLE_STORAGE_SERVER")
if GOOGLE_STORAGE_BUCKET == "" or GOOGLE_STORAGE_SERVER == "":
    err_msg = "GOOGLE_STORAGE_BUCKET or GOOGLE_STORAGE_SERVER not found in .env"
    raise Exception(err_msg)


class GCSLockAdapter:
    """Handle distributed file locking using GCS generation numbers."""

    LOCK_TIMEOUT = 300  # 5 minutes
    LOCK_FILE_MIN_LINES = 2  # Lock file format: line 1=instance_id, line 2=timestamp

    def __init__(self) -> None:
        """Initialize GCS client and bucket."""
        self.storage_client = storage.Client()
        self.bucket_name = GOOGLE_STORAGE_BUCKET
        self.bucket = self.storage_client.bucket(self.bucket_name)

    def try_acquire_lock(self, file_path: str, instance_id: str) -> bool:
        """Try to acquire lock using GCS conditional upload.

        Uses if-generation-match=0 to ensure atomic lock creation.

        Args:
            file_path: GCS object path (e.g., "events/EVENT123/CAPTURED_20241217.mp4")
            instance_id: Identifier for the instance trying to acquire the lock

        Returns:
            True if lock acquired, False otherwise

        """
        lock_path = f"{file_path}.lock"
        lock_blob = self.bucket.blob(lock_path)

        try:
            # Check if lock exists and is stale
            if lock_blob.exists():
                if self._is_lock_stale(lock_blob):
                    logging.warning(f"Removing stale lock: {lock_path}")
                    try:
                        lock_blob.delete()
                    except Exception:
                        logging.exception("Failed to delete stale lock")
                        return False
                else:
                    # Lock exists and is fresh
                    return False

            # Create lock with generation precondition
            # if_generation_match=0 means "only create if doesn't exist"
            lock_content = f"{instance_id}\n{time.time()}"

            lock_blob.upload_from_string(
                lock_content,
                content_type="text/plain",
                if_generation_match=0  # Atomic: only succeeds if blob doesn't exist
            )

        except exceptions.PreconditionFailed:
            # Another instance got the lock first
            logging.debug(f"Lock already exists: {lock_path}")
            return False
        except Exception:
            logging.exception(f"Error acquiring lock for {lock_path}")
            return False
        else:
            logging.debug(f"Lock acquired: {lock_path} by {instance_id}")
            return True


    def _is_lock_stale(self, lock_blob: storage.Blob) -> bool:
        """Check if a lock file is stale based on timeout."""
        try:
            lock_blob.reload()
            lock_content = lock_blob.download_as_text()
            lines = lock_content.split("\n")

            if len(lines) >= self.LOCK_FILE_MIN_LINES:
                lock_time = float(lines[1])
                if time.time() - lock_time > self.LOCK_TIMEOUT:
                    return True

        except Exception:
            logging.exception("Error checking lock staleness")
            # If we can't determine, assume not stale (safe default)
        return False

    def release_lock(self, file_path: str) -> None:
        """Release lock on a file."""
        lock_path = f"{file_path}.lock"
        lock_blob = self.bucket.blob(lock_path)

        try:
            if lock_blob.exists():
                lock_blob.delete()
                logging.info(f"Lock released: {lock_path}")
        except Exception:
            logging.exception(f"Error releasing lock for {lock_path}")
