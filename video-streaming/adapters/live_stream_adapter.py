"""Adapter for Google Cloud Live Stream API operations."""

import json
import logging
from pathlib import Path
from typing import Any

from google.cloud.video import live_stream_v1
from google.cloud.video.live_stream_v1.types import (
    AudioStream,
    Channel,
    ElementaryStream,
    Input,
    Manifest,
    MuxStream,
    Output,
    SegmentSettings,
    VideoStream,
)


class LiveStreamAdapter:
    """Adapter for Google Live Stream API."""

    def __init__(self, project_id: str, location: str) -> None:
        """Initialize the adapter.

        Args:
            project_id: Google Cloud project ID
            location: Google Cloud region (e.g., 'us-central1')

        """
        self.project_id = project_id
        self.location = location
        self.client = live_stream_v1.LivestreamServiceClient()
        self.parent = f"projects/{project_id}/locations/{location}"

    def create_input(
        self,
        input_id: str,
    ) -> Input:
        """Create an SRT push input endpoint.

        Args:
            input_id: Unique identifier for the input

        Returns:
            Created Input resource

        """
        input_config = live_stream_v1.Input(
            type_=live_stream_v1.Input.Type.SRT_PUSH,
            tier=live_stream_v1.Input.Tier.HD,
        )

        operation = self.client.create_input(
            parent=self.parent,
            input=input_config,
            input_id=input_id,
        )

        logging.info("Creating input: %s", input_id)
        response = operation.result(timeout=600)
        logging.info("Created input: %s", response.name)

        return response

    def create_channel(
        self,
        channel_id: str,
        input_id: str,
        output_uri: str,
        segment_duration: int = 30,
        video_bitrate_bps: int = 2000000,
        video_width: int = 1280,
        video_height: int = 720,
        video_fps: int = 30,
        audio_codec: str = "aac",
        audio_bitrate_bps: int = 128000,
        audio_channels: int = 2,
        audio_sample_rate: int = 48000,
    ) -> Channel:
        """Create a live stream channel.

        Args:
            channel_id: Unique identifier for the channel
            input_id: ID of the input to attach
            output_uri: GCS URI for output (e.g., gs://bucket/path/)
            segment_duration: Duration of each segment in seconds
            video_bitrate_bps: Video bitrate in bits per second
            video_width: Video width in pixels
            video_height: Video height in pixels
            video_fps: Video frames per second
            audio_codec: Audio codec (e.g., "aac")
            audio_bitrate_bps: Audio bitrate in bits per second
            audio_channels: Number of audio channels
            audio_sample_rate: Audio sample rate in Hz

        Returns:
            Created Channel resource

        """
        input_name = f"{self.parent}/inputs/{input_id}"

        # Configure video stream
        video_stream = VideoStream(
            h264=VideoStream.H264CodecSettings(
                bitrate_bps=video_bitrate_bps,
                frame_rate=video_fps,
                height_pixels=video_height,
                width_pixels=video_width,
            )
        )

        # Configure audio stream
        # Set channel layout based on number of channels
        if audio_channels == 2:  # noqa: PLR2004, SIM108
            channel_layout = ["fl", "fr"]  # Stereo: front left, front right
        else:
            channel_layout = ["fc"]  # Mono: front center

        audio_stream = AudioStream(
            codec=audio_codec,
            bitrate_bps=audio_bitrate_bps,
            channel_count=audio_channels,
            channel_layout=channel_layout,
            sample_rate_hertz=audio_sample_rate,
        )

        # Create elementary streams
        video_elementary = ElementaryStream(
            key="video-stream",
            video_stream=video_stream,
        )

        audio_elementary = ElementaryStream(
            key="audio-stream",
            audio_stream=audio_stream,
        )

        # Create mux stream (combines video and audio)
        mux_stream = MuxStream(
            key="mux-stream",
            container="ts",
            elementary_streams=["video-stream", "audio-stream"],
            segment_settings=SegmentSettings(
                segment_duration=f"{segment_duration}s",
            ),
        )

        # Configure manifest for HLS
        manifest = Manifest(
            file_name="manifest.m3u8",
            type_=Manifest.ManifestType.HLS,
            mux_streams=["mux-stream"],
            max_segment_count=10,
        )

        # Configure output to GCS
        output = Output(uri=output_uri)

        # Create channel configuration
        channel = Channel(
            input_attachments=[
                Channel.InputAttachment(
                    key="input",
                    input=input_name,
                )
            ],
            output=output,
            elementary_streams=[video_elementary, audio_elementary],
            mux_streams=[mux_stream],
            manifests=[manifest],
        )

        operation = self.client.create_channel(
            parent=self.parent,
            channel=channel,
            channel_id=channel_id,
        )

        logging.info("Creating channel: %s", channel_id)
        response = operation.result(timeout=600)
        logging.info("Created channel: %s", response.name)

        return response

    def start_channel(self, channel_id: str) -> Channel:
        """Start a live stream channel.

        Args:
            channel_id: ID of the channel to start

        Returns:
            Updated Channel resource

        """
        channel_name = f"{self.parent}/channels/{channel_id}"

        operation = self.client.start_channel(name=channel_name)

        logging.info("Starting channel: %s", channel_id)
        response = operation.result(timeout=600)
        logging.info("Started channel: %s", response.name)

        return response

    def stop_channel(self, channel_id: str) -> Channel:
        """Stop a live stream channel.

        Args:
            channel_id: ID of the channel to stop

        Returns:
            Updated Channel resource

        """
        channel_name = f"{self.parent}/channels/{channel_id}"

        operation = self.client.stop_channel(name=channel_name)

        logging.info("Stopping channel: %s", channel_id)
        response = operation.result(timeout=600)
        logging.info("Stopped channel: %s", response.name)

        return response

    def delete_channel(self, channel_id: str) -> None:
        """Delete a live stream channel.

        Args:
            channel_id: ID of the channel to delete

        """
        channel_name = f"{self.parent}/channels/{channel_id}"

        operation = self.client.delete_channel(name=channel_name)

        logging.info("Deleting channel: %s", channel_id)
        operation.result(timeout=600)
        logging.info("Deleted channel: %s", channel_name)

    def delete_input(self, input_id: str) -> None:
        """Delete an input endpoint.

        Args:
            input_id: ID of the input to delete

        """
        input_name = f"{self.parent}/inputs/{input_id}"

        operation = self.client.delete_input(name=input_name)

        logging.info("Deleting input: %s", input_id)
        operation.result(timeout=600)
        logging.info("Deleted input: %s", input_name)

    def get_channel(self, channel_id: str) -> Channel:
        """Get channel details.

        Args:
            channel_id: ID of the channel

        Returns:
            Channel resource

        """
        channel_name = f"{self.parent}/channels/{channel_id}"
        return self.client.get_channel(name=channel_name)

    def get_input(self, input_id: str) -> Input:
        """Get input details.

        Args:
            input_id: ID of the input

        Returns:
            Input resource

        """
        input_name = f"{self.parent}/inputs/{input_id}"
        return self.client.get_input(name=input_name)

    def list_channels(self) -> list[Channel]:
        """List all channels in the project.

        Returns:
            List of Channel resources

        """
        request = live_stream_v1.ListChannelsRequest(
            parent=self.parent,
        )

        page_result = self.client.list_channels(request=request)
        return list(page_result)

    def list_inputs(self) -> list[Input]:
        """List all inputs in the project.

        Returns:
            List of Input resources

        """
        request = live_stream_v1.ListInputsRequest(
            parent=self.parent,
        )

        page_result = self.client.list_inputs(request=request)
        return list(page_result)


class LiveStreamConfigAdapter:
    """Adapter for loading Live Stream configuration."""

    def __init__(self, config_path: str | None = None) -> None:
        """Initialize the config adapter.

        Args:
            config_path: Path to configuration file. If None, uses default.

        """
        if config_path is None:
            config_path = str(
                Path(__file__).parent.parent / "config" / "livestream_settings.json"
            )
        self.config_path = config_path
        self._config: dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from file."""
        try:
            with Path(self.config_path).open() as f:
                self._config = json.load(f)
            logging.info("Loaded config from: %s", self.config_path)
        except FileNotFoundError:
            logging.warning(
                "Config file not found: %s, using empty config", self.config_path
            )
            self._config = {}

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value

        """
        return self._config.get(key, default)

    def get_int(self, key: str, default: int = 0) -> int:
        """Get configuration value as integer.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value as integer

        """
        value = self._config.get(key, default)
        return int(value) if value is not None else default

    def get_str(self, key: str, default: str = "") -> str:
        """Get configuration value as string.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value as string

        """
        value = self._config.get(key, default)
        return str(value) if value is not None else default
