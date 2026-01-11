"""Integration example showing hybrid video capture approach.

This example demonstrates how to use both traditional Python capture
and Google Live Stream API capture in the same application.
"""

import asyncio
import logging
import os
from typing import Any

from video_streaming.services import LiveStreamService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


class HybridVideoCapture:
    """Hybrid video capture service supporting multiple capture methods."""

    def __init__(self) -> None:
        """Initialize the hybrid capture service."""
        self.live_stream_service = None
        # Note: VideoService would be imported here if using the traditional capture
        # from video_service.services import VideoService
        # self.video_service = VideoService()

    async def capture_video(
        self,
        event: dict[str, Any],
        clip_duration: int = 30,
        use_live_stream_api: bool = False,
    ) -> dict[str, Any]:
        """Capture video using the appropriate method.

        Args:
            event: Event details including id and configuration
            clip_duration: Duration of each video clip in seconds
            use_live_stream_api: If True, use Live Stream API; otherwise use traditional

        Returns:
            Dictionary containing capture information

        """
        if use_live_stream_api:
            return await self._capture_with_live_stream_api(event, clip_duration)
        return await self._capture_with_traditional(event, clip_duration)

    async def _capture_with_live_stream_api(
        self,
        event: dict[str, Any],
        clip_duration: int,
    ) -> dict[str, Any]:
        """Capture video using Google Live Stream API.

        Args:
            event: Event details
            clip_duration: Clip duration in seconds

        Returns:
            Capture information

        """
        logging.info(
            "Using Google Live Stream API for event: %s",
            event.get("id"),
        )

        if self.live_stream_service is None:
            self.live_stream_service = LiveStreamService()

        try:
            # Create and start channel
            channel_info = await self.live_stream_service.create_and_start_channel(
                event_id=event["id"],
                clip_duration=clip_duration,
            )

            return {
                "method": "live_stream_api",
                "status": "success",
                "event_id": event["id"],
                "channel_info": channel_info,
                "message": f"Live stream channel created. Stream to: {channel_info['srt_push_url']}",
            }

        except Exception as e:
            logging.exception("Failed to create Live Stream channel")
            return {
                "method": "live_stream_api",
                "status": "error",
                "event_id": event["id"],
                "error": str(e),
            }

    async def _capture_with_traditional(
        self,
        event: dict[str, Any],
        clip_duration: int,
    ) -> dict[str, Any]:
        """Capture video using traditional Python method.

        Args:
            event: Event details
            clip_duration: Clip duration in seconds

        Returns:
            Capture information

        """
        logging.info(
            "Using traditional Python capture for event: %s",
            event.get("id"),
        )

        # This would call the traditional VideoService
        # result = await self.video_service.capture_video(
        #     token=token,
        #     event=event,
        #     status_type="video_status",
        #     instance_name="hybrid-worker",
        # )

        # Simulated response for demonstration
        return {
            "method": "traditional",
            "status": "success",
            "event_id": event["id"],
            "message": "Traditional capture would be initiated here",
        }

    async def stop_capture(
        self,
        event: dict[str, Any],
        method: str = "auto",
    ) -> dict[str, Any]:
        """Stop video capture.

        Args:
            event: Event details
            method: Method to stop ('live_stream_api', 'traditional', or 'auto')

        Returns:
            Stop operation result

        """
        if method == "live_stream_api" or (
            method == "auto" and self.live_stream_service is not None
        ):
            try:
                await self.live_stream_service.stop_channel(event_id=event["id"])
                return {
                    "status": "success",
                    "event_id": event["id"],
                    "message": "Live stream channel stopped",
                }
            except Exception as e:
                logging.exception("Failed to stop Live Stream channel")
                return {
                    "status": "error",
                    "event_id": event["id"],
                    "error": str(e),
                }

        return {
            "status": "success",
            "event_id": event["id"],
            "message": "Traditional capture stop would be handled here",
        }

    async def cleanup(self, event: dict[str, Any]) -> None:
        """Cleanup resources for an event.

        Args:
            event: Event details

        """
        if self.live_stream_service is not None:
            try:
                await self.live_stream_service.cleanup_resources(event_id=event["id"])
                logging.info(
                    "Cleaned up Live Stream resources for event: %s", event["id"]
                )
            except Exception:
                logging.exception("Failed to cleanup Live Stream resources")


async def main() -> None:
    """Run the integration example."""
    # Initialize hybrid capture service
    service = HybridVideoCapture()

    # Example event configuration
    event_traditional = {
        "id": "event-001-traditional",
        "name": "Test Event - Traditional",
        "use_live_stream_api": False,
    }

    event_live_stream = {
        "id": "event-002-livestream",
        "name": "Test Event - Live Stream API",
        "use_live_stream_api": True,
    }

    # Scenario 1: Use traditional capture
    print("\n=== Scenario 1: Traditional Python Capture ===")
    result1 = await service.capture_video(
        event=event_traditional,
        clip_duration=30,
        use_live_stream_api=False,
    )
    print(f"Result: {result1}")

    # Scenario 2: Use Live Stream API
    print("\n=== Scenario 2: Google Live Stream API Capture ===")
    result2 = await service.capture_video(
        event=event_live_stream,
        clip_duration=30,
        use_live_stream_api=True,
    )
    print(f"Result: {result2}")

    if result2["status"] == "success":
        print(f"\nSRT Push URL: {result2['channel_info']['srt_push_url']}")
        print(f"Output URI: {result2['channel_info']['output_uri']}")

        # Simulate some streaming time
        print("\n(Stream video to the SRT Push URL now)")
        await asyncio.sleep(5)

        # Stop the channel
        print("\n=== Stopping Live Stream Channel ===")
        stop_result = await service.stop_capture(
            event=event_live_stream,
            method="live_stream_api",
        )
        print(f"Stop Result: {stop_result}")

        # Cleanup
        print("\n=== Cleaning up resources ===")
        await service.cleanup(event=event_live_stream)

    print("\n=== Example Complete ===")


async def decision_logic_example() -> None:
    """Example of decision logic for choosing capture method."""
    # Example scenarios where each method is preferred

    scenarios = [
        {
            "name": "24/7 Continuous Monitoring",
            "duration_hours": 720,  # 30 days
            "events_per_month": 1,
            "recommendation": "traditional",
            "reason": "Cost-effective for continuous operation",
        },
        {
            "name": "Sporting Event (2 hours)",
            "duration_hours": 2,
            "events_per_month": 10,
            "recommendation": "live_stream_api",
            "reason": "Low total hours, event-based, minimal infrastructure",
        },
        {
            "name": "Multi-camera Setup",
            "duration_hours": 8,
            "events_per_month": 20,
            "recommendation": "traditional",
            "reason": "High volume requires compute anyway, custom processing",
        },
        {
            "name": "Emergency Backup Camera",
            "duration_hours": 1,
            "events_per_month": 2,
            "recommendation": "live_stream_api",
            "reason": "Rarely used, quick deployment, no maintenance",
        },
    ]

    print("\n=== Capture Method Decision Logic ===\n")

    for scenario in scenarios:
        print(f"Scenario: {scenario['name']}")
        print(f"  Duration: {scenario['duration_hours']} hours/event")
        print(f"  Frequency: {scenario['events_per_month']} events/month")
        print(f"  Recommendation: {scenario['recommendation'].upper()}")
        print(f"  Reason: {scenario['reason']}")
        print()


if __name__ == "__main__":
    # Run main example
    asyncio.run(main())

    # Show decision logic
    asyncio.run(decision_logic_example())
