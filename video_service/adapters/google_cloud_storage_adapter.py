"""Module for google cloud storage adapter."""

import logging
import os
from pathlib import Path

from google.cloud import storage


class GoogleCloudStorageAdapter:
    """Class representing google cloud storage."""

    def get_trigger_line_file_url(self, event: dict) -> str:
        """Get url to latest trigger line photo."""
        file_identifier = f"{event['id']}/trigger_line"
        try:
            # Lists files in a directory sorted by creation date, newest first."""
            files = self.list_blobs(file_identifier)
            sorted_files = []
            if len(files) > 0:
                sorted_files = sorted(files, key=lambda x: x["name"], reverse=True)
                if len(sorted_files) > 1:
                    for f in sorted_files[1:]:
                        self.move_blob(f["name"], f"archive/{f['name']}")
            return sorted_files[0]["url"]
        except Exception:
            logging.exception("Error getting photos")
            return ""


    def upload_blob(self, destination_folder: str, source_file_name: str) -> str:
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
                destination_blob_name = f"{destination_folder}/{Path(source_file_name).name}"
            blob = bucket.blob(destination_blob_name)
            blob.upload_from_filename(source_file_name)
        except Exception as e:
            logging.exception(servicename)
            raise Exception(servicename) from e
        return (
            f"{storage_server}/{storage_bucket}/{destination_blob_name}"
        )

    def upload_blob_bytes(self, destination_folder: str, filename: str, data: bytes, content_type: str, metadata: dict) -> str:
        """Upload a byte object to the bucket, return URL to uploaded file."""
        servicename = "GoogleCloudStorageAdapter.upload_blob"
        storage_bucket = os.getenv("GOOGLE_STORAGE_BUCKET", "")
        storage_server = os.getenv("GOOGLE_STORAGE_SERVER", "")
        if storage_bucket == "" or storage_server == "":
            err_msg = "GOOGLE_STORAGE_BUCKET or GOOGLE_STORAGE_SERVER not found in .env"
            raise Exception(err_msg)

        try:
            storage_client = storage.Client()
            bucket = storage_client.bucket(storage_bucket)
            destination_blob_name = f"{destination_folder}/{filename}" if destination_folder else filename
            blob = bucket.blob(destination_blob_name)
            if metadata:
                blob.metadata = metadata
            blob.upload_from_string(data, content_type=content_type)
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

    def list_blobs(self, prefix: str) -> list[dict]:
        """List all blobs in the bucket that begin with the prefix."""
        servicename = "GoogleCloudStorageAdapter.get_blobs"
        storage_bucket = os.getenv("GOOGLE_STORAGE_BUCKET", "")
        if storage_bucket == "":
            err_msg = "GOOGLE_STORAGE_BUCKET not found in .env"
            raise Exception(err_msg)

        try:
            storage_client = storage.Client()
            bucket = storage_client.bucket(storage_bucket)
            blobs = bucket.list_blobs(prefix=prefix)

            return [
                {"name": f.name, "url": f.public_url}
                for f in blobs
            ]
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
