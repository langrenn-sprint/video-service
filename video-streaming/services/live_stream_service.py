"""Service for managing Google Live Stream API operations."""

import asyncio
import logging
import os
from typing import Any

from video_streaming.adapters import LiveStreamAdapter, LiveStreamConfigAdapter


class LiveStreamService:
    """Service for capturing video using Google Live Stream API.

    This service provides an alternative to the traditional Python-based
    video capture (cv2.VideoCapture). It uses Google Cloud Live Stream API
    to capture video streams from SRT Push sources and store them directly
    to cloud storage with configurable clip duration.

    """

    def __init__(
        self,
        project_id: str | None = None,
        location: str | None = None,
        bucket_name: str | None = None,
    ) -> None:
        """Initialize the Live Stream Service.

        Args:
            project_id: Google Cloud project ID. If None, uses config or env var.
            location: Google Cloud region. If None, uses config or env var.
            bucket_name: Cloud Storage bucket name. If None, uses config or env var.

        """
        self.config = LiveStreamConfigAdapter()

        self.project_id = (
            project_id
            or self.config.get_str("GOOGLE_CLOUD_PROJECT")
            or os.getenv("GOOGLE_CLOUD_PROJECT", "")
        )

        self.location = (
            location
            or self.config.get_str("GOOGLE_CLOUD_REGION", "us-central1")
            or os.getenv("GOOGLE_CLOUD_REGION", "us-central1")
        )

        self.bucket_name = (
            bucket_name
            or self.config.get_str("GOOGLE_STORAGE_BUCKET")
            or os.getenv("GOOGLE_STORAGE_BUCKET", "")
        )

        if not self.project_id:
            error_msg = "GOOGLE_CLOUD_PROJECT must be set"
            raise ValueError(error_msg)

        if not self.bucket_name:
            error_msg = "GOOGLE_STORAGE_BUCKET must be set"
            raise ValueError(error_msg)

        self.adapter = LiveStreamAdapter(self.project_id, self.location)

        logging.info(
            "Initialized LiveStreamService for project=%s, location=%s, bucket=%s",
            self.project_id,
            self.location,
            self.bucket_name,
        )

    async def create_and_start_channel(
        self,
        event_id: str,
        clip_duration: int | None = None,
    ) -> dict[str, Any]:
        """Create and start a live stream channel for an event.

        This method creates an SRT Push input endpoint and a channel that
        captures the stream and stores it to cloud storage.

        Args:
            event_id: Unique identifier for the event
            clip_duration: Duration of each video clip in seconds.
                          If None, uses config value (default: 30)

        Returns:
            Dictionary containing channel information:
                - channel_id: ID of the created channel
                - input_id: ID of the created input
                - srt_push_url: URL for streaming via SRT Push
                - output_uri: GCS URI where videos are stored
                - segment_duration: Duration of each segment in seconds

        """
        if clip_duration is None:
            clip_duration = self.config.get_int("VIDEO_CLIP_DURATION", 30)

        # Generate resource IDs
        input_id = (
            f"{self.config.get_str('LIVESTREAM_INPUT_PREFIX', 'srt-input')}-{event_id}"
        )
        channel_id = f"{self.config.get_str('LIVESTREAM_CHANNEL_PREFIX', 'video-capture')}-{event_id}"

        # Create output path in cloud storage
        output_path_template = self.config.get_str(
            "VIDEO_OUTPUT_PATH_TEMPLATE", "events/{event_id}/captured/"
        )
        output_path = output_path_template.format(event_id=event_id)
        output_uri = f"gs://{self.bucket_name}/{output_path}"

        try:
            # Create input endpoint
            logging.info("Creating input endpoint for event: %s", event_id)
            input_resource = await asyncio.to_thread(
                self.adapter.create_input,
                input_id=input_id,
            )

            # Create channel
            logging.info("Creating channel for event: %s", event_id)
            await asyncio.to_thread(
                self.adapter.create_channel,
                channel_id=channel_id,
                input_id=input_id,
                output_uri=output_uri,
                segment_duration=clip_duration,
            )

            # Start channel
            logging.info("Starting channel for event: %s", event_id)
            await asyncio.to_thread(
                self.adapter.start_channel,
                channel_id=channel_id,
            )

        except Exception:
            logging.exception(
                "Failed to create and start channel for event: %s", event_id
            )
            # Cleanup on failure
            try:
                await self.cleanup_resources(event_id)
            except Exception:
                logging.exception("Failed to cleanup resources after error")
            raise
        else:
            # Get SRT Push URL from input resource
            srt_push_url = input_resource.uri

            logging.info(
                "Successfully created and started channel for event: %s, SRT URL: %s",
                event_id,
                srt_push_url,
            )

            return {
                "channel_id": channel_id,
                "input_id": input_id,
                "srt_push_url": srt_push_url,
                "output_uri": output_uri,
                "segment_duration": clip_duration,
                "event_id": event_id,
            }

    async def stop_channel(self, event_id: str) -> None:
        """Stop a live stream channel.

        Args:
            event_id: Unique identifier for the event

        """
        channel_id = f"{self.config.get_str('LIVESTREAM_CHANNEL_PREFIX', 'video-capture')}-{event_id}"

        logging.info("Stopping channel for event: %s", event_id)
        await asyncio.to_thread(
            self.adapter.stop_channel,
            channel_id=channel_id,
        )
        logging.info("Successfully stopped channel for event: %s", event_id)

    async def cleanup_resources(self, event_id: str) -> None:
        """Delete channel and input resources for an event.

        Args:
            event_id: Unique identifier for the event

        """
        channel_id = f"{self.config.get_str('LIVESTREAM_CHANNEL_PREFIX', 'video-capture')}-{event_id}"
        input_id = (
            f"{self.config.get_str('LIVESTREAM_INPUT_PREFIX', 'srt-input')}-{event_id}"
        )

        try:
            logging.info("Cleaning up resources for event: %s", event_id)

            # Stop channel first if it's running
            try:
                await asyncio.to_thread(
                    self.adapter.stop_channel,
                    channel_id=channel_id,
                )
            except Exception:
                logging.warning("Channel may already be stopped or not exist")

            # Delete channel
            try:
                await asyncio.to_thread(
                    self.adapter.delete_channel,
                    channel_id=channel_id,
                )
            except Exception:
                logging.warning("Failed to delete channel: %s", channel_id)

            # Delete input
            try:
                await asyncio.to_thread(
                    self.adapter.delete_input,
                    input_id=input_id,
                )
            except Exception:
                logging.warning("Failed to delete input: %s", input_id)

            logging.info("Successfully cleaned up resources for event: %s", event_id)

        except Exception:
            logging.exception("Error during cleanup for event: %s", event_id)
            raise

    async def get_channel_status(self, event_id: str) -> dict[str, Any]:
        """Get the status of a live stream channel.

        Args:
            event_id: Unique identifier for the event

        Returns:
            Dictionary containing channel status information

        """
        channel_id = f"{self.config.get_str('LIVESTREAM_CHANNEL_PREFIX', 'video-capture')}-{event_id}"

        channel = await asyncio.to_thread(
            self.adapter.get_channel,
            channel_id=channel_id,
        )

        return {
            "channel_id": channel_id,
            "event_id": event_id,
            "state": channel.streaming_state.name,
            "streaming_error": str(channel.streaming_error)
            if channel.streaming_error
            else None,
        }

    async def list_active_channels(self) -> list[dict[str, Any]]:
        """List all active channels.

        Returns:
            List of dictionaries containing channel information

        """
        channels = await asyncio.to_thread(self.adapter.list_channels)

        result = []
        for channel in channels:
            # Extract event_id from channel name
            channel_name_parts = channel.name.split("/")
            full_channel_id = channel_name_parts[-1]

            prefix = self.config.get_str("LIVESTREAM_CHANNEL_PREFIX", "video-capture")
            event_id = (
                full_channel_id.replace(f"{prefix}-", "", 1)
                if prefix in full_channel_id
                else full_channel_id
            )

            result.append(
                {
                    "channel_id": full_channel_id,
                    "event_id": event_id,
                    "state": channel.streaming_state.name,
                    "name": channel.name,
                }
            )

        return result
