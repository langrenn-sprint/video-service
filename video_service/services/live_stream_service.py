"""Service for managing Google Live Stream API operations."""

import asyncio
import logging
import os
from typing import Any

from dotenv import load_dotenv

from video_service.adapters import (
    ConfigAdapter,
    LiveStreamAdapter,
)


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
        load_dotenv()

        self.project_id = (
            project_id
            or os.getenv("GOOGLE_CLOUD_PROJECT", "")
        )

        self.location = (
            location
            or os.getenv("GOOGLE_CLOUD_REGION", "europe-north1")
        )

        self.bucket_name = (
            bucket_name
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
        token: str,
        event: dict,
    ) -> dict[str, Any]:
        """Create and start a live stream channel for an event.

        This method creates an SRT Push input endpoint and a channel that
        captures the stream and stores it to cloud storage.

        Args:
            token: Authentication token
            event: Unique identifier for the event

        Returns:
            Dictionary containing channel information:
                - channel_id: ID of the created channel
                - input_id: ID of the created input
                - srt_push_url: URL for streaming via SRT Push
                - output_uri: GCS URI where videos are stored
                - segment_duration: Duration of each segment in seconds

        """
        clip_duration = await ConfigAdapter().get_config_int(
            token, event["id"], "VIDEO_CLIP_DURATION"
        )

        # Generate resource IDs
        input_id = f"{await ConfigAdapter().get_config(token, event['id'], 'LIVESTREAM_INPUT_PREFIX')}-{event['id']}"
        channel_id = f"{await ConfigAdapter().get_config(token, event['id'], 'LIVESTREAM_CHANNEL_PREFIX')}-{event["id"]}"

        # Create output path in cloud storage
        output_path_template = await ConfigAdapter().get_config(
            token, event["id"], "VIDEO_OUTPUT_PATH_TEMPLATE"
        )
        output_path = output_path_template.format(event_id=event["id"])
        output_uri = f"gs://{self.bucket_name}/{output_path}"

        try:
            # Create input endpoint
            logging.info("Creating input endpoint for event: %s", event["id"])
            input_resource = await asyncio.to_thread(
                self.adapter.create_input,
                input_id=input_id,
            )

            # Create channel
            logging.info("Creating channel for event: %s", event["id"])
            await asyncio.to_thread(
                self.adapter.create_channel,
                channel_id=channel_id,
                input_id=input_id,
                output_uri=output_uri,
                segment_duration=clip_duration,
                video_bitrate_bps=await ConfigAdapter().get_config_int(token, event["id"], "VIDEO_BITRATE_BPS"),
                video_width=await ConfigAdapter().get_config_int(token, event["id"], "VIDEO_WIDTH"),
                video_height=await ConfigAdapter().get_config_int(token, event["id"], "VIDEO_HEIGHT"),
                video_fps=await ConfigAdapter().get_config_int(token, event["id"], "VIDEO_CLIP_FPS"),
                audio_codec="aac",
                audio_bitrate_bps=128000,
                audio_channels=2,
                audio_sample_rate=48000,
            )

            # Start channel
            logging.info("Starting channel for event: %s", event["id"])
            await asyncio.to_thread(
                self.adapter.start_channel,
                channel_id=channel_id,
            )

        except Exception:
            logging.exception(
                "Failed to create and start channel for event: %s", event["id"]
            )
            # Cleanup on failure
            try:
                await self.cleanup_resources(token, event)
            except Exception:
                logging.exception("Failed to cleanup resources after error")
            raise
        else:
            # Get SRT Push URL from input resource
            srt_push_url = input_resource.uri

            logging.info(
                "Successfully created and started channel for event: %s, SRT URL: %s",
                event["id"],
                srt_push_url,
            )

            return {
                "channel_id": channel_id,
                "input_id": input_id,
                "srt_push_url": srt_push_url,
                "output_uri": output_uri,
                "segment_duration": clip_duration,
                "event_id": event["id"],
            }

    async def stop_channel(self, token: str, event: dict) -> None:
        """Stop a live stream channel.

        Args:
            token: Authentication token
            event: Event dictionary containing event ID

        """
        channel_id = f"{await ConfigAdapter().get_config(token, event['id'], 'LIVESTREAM_CHANNEL_PREFIX')}-{event['id']}"

        logging.info("Stopping channel for event: %s", event["id"])
        await asyncio.to_thread(
            self.adapter.stop_channel,
            channel_id=channel_id,
        )
        logging.info("Successfully stopped channel for event: %s", event["id"])

    async def cleanup_resources(self, token: str, event: dict) -> None:
        """Delete channel and input resources for an event.

        Args:
            token: Authentication token
            event: Event dictionary containing event ID

        """
        channel_id = f"{await ConfigAdapter().get_config(token, event['id'], 'LIVESTREAM_CHANNEL_PREFIX')}-{event['id']}"
        input_id = (
            f"{await ConfigAdapter().get_config(token, event['id'], 'LIVESTREAM_INPUT_PREFIX')}-{event['id']}"
        )

        try:
            logging.info("Cleaning up resources for event: %s", event["id"])

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

            logging.info("Successfully cleaned up resources for event: %s", event["id"])

        except Exception:
            logging.exception("Error during cleanup for event: %s", event["id"])
            raise

    async def get_channel_status(self, token: str, event: dict) -> dict[str, Any]:
        """Get the status of a live stream channel.

        Args:
            token: Authentication token
            event: Event dictionary containing event ID
        Returns:
            Dictionary containing channel status information

        """
        channel_id = f"{await ConfigAdapter().get_config(token, event['id'], 'LIVESTREAM_CHANNEL_PREFIX')}-{event['id']}"

        channel = await asyncio.to_thread(
            self.adapter.get_channel,
            channel_id=channel_id,
        )

        return {
            "channel_id": channel_id,
            "event_id": event["id"],
            "state": channel.streaming_state.name,
            "streaming_error": str(channel.streaming_error)
            if channel.streaming_error
            else None,
        }

    async def list_active_channels(self) -> list[dict[str, Any]]:
        """List all active channels.

        Args:
            token: Authentication token
        Returns:
            List of dictionaries containing channel information

        """
        channels = await asyncio.to_thread(self.adapter.list_channels)

        result = []
        for channel in channels:
            # Extract event_id from channel name
            channel_name_parts = channel.name.split("/")
            full_channel_id = channel_name_parts[-1]

            # Note: Without event context, using a default prefix
            # This method may need refactoring to get config per event
            prefix = "video-capture"
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
