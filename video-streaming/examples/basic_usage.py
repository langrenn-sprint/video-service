"""Example script for using Google Live Stream API for video capture.

This example demonstrates how to:
1. Create and start a live stream channel
2. Get the SRT Push URL for streaming
3. Monitor channel status
4. Stop and cleanup resources

Usage:
    python -m video_streaming.examples.basic_usage
"""

import asyncio
import logging
import os

from video_streaming.services.live_stream_service import LiveStreamService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


async def main() -> None:
    """Run the example."""
    # Initialize service
    # These can also be set via config file or environment variables
    service = LiveStreamService(
        project_id=os.getenv("GOOGLE_CLOUD_PROJECT"),
        location=os.getenv("GOOGLE_CLOUD_REGION", "us-central1"),
        bucket_name=os.getenv("GOOGLE_STORAGE_BUCKET"),
    )

    event_id = "test-event-001"
    clip_duration = 30  # 30 seconds per clip

    try:
        # Step 1: Create and start channel
        print(f"\n=== Creating channel for event: {event_id} ===")
        channel_info = await service.create_and_start_channel(
            event_id=event_id,
            clip_duration=clip_duration,
        )

        print("\n✓ Channel created successfully!")
        print(f"  Channel ID: {channel_info['channel_id']}")
        print(f"  Input ID: {channel_info['input_id']}")
        print(f"  SRT Push URL: {channel_info['srt_push_url']}")
        print(f"  Output URI: {channel_info['output_uri']}")
        print(f"  Segment Duration: {channel_info['segment_duration']}s")

        print("\n=== Start streaming to the SRT Push URL ===")
        print(f"Use this command with FFmpeg:")
        print(f"  ffmpeg -re -i input.mp4 -c copy -f mpegts '{channel_info['srt_push_url']}'")

        # Step 2: Monitor status
        print("\n=== Checking channel status ===")
        status = await service.get_channel_status(event_id=event_id)
        print(f"  Status: {status['state']}")
        if status['streaming_error']:
            print(f"  Error: {status['streaming_error']}")

        # Step 3: List active channels
        print("\n=== Listing all active channels ===")
        channels = await service.list_active_channels()
        for ch in channels:
            print(f"  - {ch['event_id']}: {ch['state']}")

        # Wait for user input before stopping
        input("\nPress Enter to stop and cleanup the channel...")

        # Step 4: Stop and cleanup
        print(f"\n=== Stopping channel for event: {event_id} ===")
        await service.stop_channel(event_id=event_id)
        print("✓ Channel stopped")

        print(f"\n=== Cleaning up resources for event: {event_id} ===")
        await service.cleanup_resources(event_id=event_id)
        print("✓ Resources cleaned up")

        print("\n=== Video clips are stored in ===")
        print(f"  gs://{service.bucket_name}/events/{event_id}/captured/")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        logging.exception("Error in example")

        # Cleanup on error
        try:
            await service.cleanup_resources(event_id=event_id)
        except Exception:
            logging.exception("Failed to cleanup after error")


if __name__ == "__main__":
    asyncio.run(main())
