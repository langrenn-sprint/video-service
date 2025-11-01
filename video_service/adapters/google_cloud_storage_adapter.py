"""Module for google cloud storage adapter."""

import logging
import os
from pathlib import Path

from google.api_core.exceptions import Forbidden, NotFound
from google.cloud import storage


class GoogleCloudStorageAdapter:

    """Class representing google cloud storage."""

    def upload_blob(
            self,
            event_id: str,
            destination_folder: str,
            source_file_name: str,
        ) -> str:
        """Upload a file to the bucket, return URL to uploaded file."""
        servicename = "GoogleCloudStorageAdapter.upload_blob"
        storage_bucket = os.getenv("GOOGLE_STORAGE_BUCKET", "")
        storage_server = os.getenv("GOOGLE_STORAGE_SERVER", "")
        if storage_bucket == "" or storage_server == "":
            err_msg = "GOOGLE_STORAGE_BUCKET or GOOGLE_STORAGE_SERVER not found in .env"
            raise Exception(err_msg)

        try:

            storage_client = storage.Client()
            bucket = storage_client.bucket(storage_bucket)
            destination_blob_name = f"{Path(source_file_name).name}"
            if destination_folder != "":
                destination_blob_name = (
                    f"{event_id}/{destination_folder}/{Path(source_file_name).name}"
                )
            blob = bucket.blob(destination_blob_name)
            blob.upload_from_filename(source_file_name)
        except Exception as e:
            logging.exception(servicename)
            raise Exception(servicename) from e
        return (
            f"{storage_server}/{storage_bucket}/{destination_blob_name}"
        )

    def upload_blob_bytes(
            self,
            event_id: str,
            destination_folder: str,
            filename: str,
            data: bytes,
            content_type: str,
            metadata: dict,
        ) -> str:
        """Upload a byte object to the bucket, return URL to uploaded file."""
        servicename = "GoogleCloudStorageAdapter.upload_blob"
        storage_bucket = os.getenv("GOOGLE_STORAGE_BUCKET", "")
        storage_server = os.getenv("GOOGLE_STORAGE_SERVER", "")
        if storage_bucket == "" or storage_server == "":
            err_msg = "GOOGLE_STORAGE_BUCKET or GOOGLE_STORAGE_SERVER not found in .env"
            raise Exception(err_msg)

        storage_client = storage.Client()
        bucket = storage_client.bucket(storage_bucket)

        try:
            destination_blob_name = (
                f"{event_id}/{destination_folder}/{filename}"
            )
            blob = bucket.blob(destination_blob_name)
            if metadata:
                blob.metadata = metadata
            blob.upload_from_string(data, content_type=content_type)
        except Forbidden as e:
            informasjon = f"{servicename} Access denied listing blobs for {bucket.name}"
            logging.exception(informasjon)
            raise Exception(informasjon) from e
        except NotFound as e:
            informasjon = f"{servicename} Bucket {bucket.name} not found"
            logging.exception(informasjon)
            raise Exception(informasjon) from e
        except Exception as e:
            logging.exception(servicename)
            raise Exception(servicename) from e
        return (
            f"{storage_server}/{storage_bucket}/{destination_blob_name}"
        )

    def move_blob(self, source_blob_name: str, destination_blob_name: str) -> str:
        """Move a blob within the bucket, return URL to moved file."""
        servicename = "GoogleCloudStorageAdapter.move_blob"
        storage_bucket = os.getenv("GOOGLE_STORAGE_BUCKET", "")
        storage_server = os.getenv("GOOGLE_STORAGE_SERVER", "")
        if storage_bucket == "" or storage_server == "":
            err_msg = "GOOGLE_STORAGE_BUCKET or GOOGLE_STORAGE_SERVER not found in .env"
            raise Exception(err_msg)

        try:
            storage_client = storage.Client()
            bucket = storage_client.bucket(storage_bucket)
            blob = bucket.blob(source_blob_name)
            new_blob = bucket.rename_blob(blob, destination_blob_name)
        except Exception as e:
            logging.exception(servicename)
            raise Exception(servicename) from e
        return (
            f"{storage_server}/{storage_bucket}/{new_blob.name}"
        )


    def move_to_error_archive(self, event_id: str, filename: str) -> str:
        """Move photo to local error archive."""
        destination_file = ""
        try:
            self.move_blob(
                f"{event_id}/CAPTURE/{filename}",
                f"{event_id}/CAPTURE_ERROR/{filename}",
            )
        except Exception:
            logging.exception("Error moving photo to error archive.")
        return destination_file


    def move_to_capture_archive(self, event_id: str, filename: str) -> str:
        """Move photo to local archive."""
        destination_file = ""
        try:
            self.move_blob(
                f"{event_id}/CAPTURE/{filename}",
                f"{event_id}/CAPTURE_ARCHIVE/{filename}",
            )
        except Exception:
            logging.exception("Error moving photo to archive.")
        return destination_file

    def list_blobs(self, event_id: str, prefix: str) -> list[dict]:
        """List all blobs in the bucket that begin with the prefix."""
        servicename = "GoogleCloudStorageAdapter.get_blobs"
        logging.debug(f"{servicename} event_id: {event_id}, prefix: {prefix}")
        storage_bucket = os.getenv("GOOGLE_STORAGE_BUCKET", "")
        if storage_bucket == "":
            err_msg = "GOOGLE_STORAGE_BUCKET not found in .env"
            raise Exception(err_msg)
        storage_client = storage.Client()
        bucket = storage_client.bucket(storage_bucket)

        try:
            blobs = list(bucket.list_blobs(prefix=f"{event_id}/{prefix}"))
            logging.debug(f"{servicename} found {len(blobs)} blobs from {event_id}/{prefix}.")

            return [
                {"name": f.name, "url": f.public_url}
                for f in blobs
            ]
        except Forbidden as e:
            informasjon = f"{servicename} Access denied listing blobs for {bucket.name}"
            logging.exception(informasjon)
            raise Exception(informasjon) from e
        except NotFound as e:
            informasjon = f"{servicename} Bucket {bucket.name} not found"
            logging.exception(informasjon)
            raise Exception(informasjon) from e
        except Exception as e:
            logging.exception(servicename)
            raise Exception(servicename) from e

    def delete_blob(self, blob_name: str) -> None:
        """Delete a blob in the bucket."""
        servicename = "GoogleCloudStorageAdapter.delete_blob"
        storage_bucket = os.getenv("GOOGLE_STORAGE_BUCKET", "")
        if storage_bucket == "":
            err_msg = "GOOGLE_STORAGE_BUCKET not found in .env"
            raise Exception(err_msg)

        try:
            storage_client = storage.Client()
            bucket = storage_client.bucket(storage_bucket)
            blob = bucket.blob(blob_name)
            blob.delete()
        except Exception as e:
            logging.exception(servicename)
            raise Exception(servicename) from e
