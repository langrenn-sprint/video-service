"""Module for application looking at video and detecting line crossings."""

import asyncio
import logging
import os
import socket
from http import HTTPStatus
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv

from video_service.adapters import (
    ConfigAdapter,
    EventsAdapter,
    StatusAdapter,
    UserAdapter,
)
from video_service.services import VideoService, VisionAIService

# Import video-streaming module for CAPTURE_SRT mode
try:
    from video_streaming.services import LiveStreamService
    LIVESTREAM_AVAILABLE = True
except ImportError:
    LIVESTREAM_AVAILABLE = False
    logging.warning("video-streaming module not available. CAPTURE_SRT mode will not work.")

# get base settings
load_dotenv()
CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}
event = {"id": ""}
status_type = ""
STATUS_INTERVAL = 60

# set up logging
LOGGING_LEVEL = os.getenv("LOGGING_LEVEL", "INFO")
logging.basicConfig(
    level=LOGGING_LEVEL,
    format="%(asctime)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
# Separate logging for errors
file_handler = RotatingFileHandler("error.log", maxBytes=1024 * 1024, backupCount=5)
file_handler.setLevel(logging.ERROR)
# Create a formatter with the desired format
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
logging.getLogger().addHandler(file_handler)

MODE = os.getenv("MODE", "DUMMY")
# Generate from hostname and PID
instance_name = ""
if os.getenv("K_REVISION"):
    instance_name = str(os.getenv("K_REVISION"))
else:
    instance_name = f"{socket.gethostname()}"

async def main() -> None:
    """CLI for analysing video stream."""
    token = ""
    event = {}
    status_type = ""
    try:
        try:
            # login to data-source
            token = await do_login()
            event = await get_event(token)

            if MODE not in ["CAPTURE_LOCAL", "CAPTURE_SRT", "DETECT"]:
                informasjon = f"Invalid mode {MODE} - no video processing will be done."
                raise Exception(informasjon)

            information = (f"{instance_name} er klar.")
            status_type += await ConfigAdapter().get_config(
                token, event["id"], "VIDEO_SERVICE_STATUS_TYPE"
            ) + f"_{MODE}"
            await StatusAdapter().create_status(
                token, event, status_type, information, event
            )

            i = 0
            while True:
                try:
                    if i > STATUS_INTERVAL:
                        informasjon = f"{instance_name} er klar."
                        await StatusAdapter().create_status(
                            token, event, status_type, informasjon, event
                        )
                        i = 0
                    else:
                        i += 1
                    await run_the_video_service(token, event, status_type, instance_name)
                    # service ready!
                    await ConfigAdapter().update_config(
                        token, event["id"], f"{MODE}_VIDEO_SERVICE_AVAILABLE", "True"
                    )
                except Exception as e:
                    err_string = str(e)
                    logging.exception(err_string)
                    # try new login if token expired (401 error)
                    if str(HTTPStatus.UNAUTHORIZED.value) in err_string:
                        token = await do_login()
                    else:
                        raise Exception(err_string) from e
                await asyncio.sleep(5)

        except Exception as e:
            err_string = str(e)
            logging.exception(err_string)
            await StatusAdapter().create_status(
                token, event, status_type, "Critical Error - exiting program", {"error": err_string}
            )
    except asyncio.CancelledError:
        await StatusAdapter().create_status(
            token, event, status_type, f"{instance_name} was cancelled (ctrl-c pressed).", {}
        )
    await ConfigAdapter().update_config(
        token, event["id"], f"{MODE}_VIDEO_SERVICE_RUNNING", "False"
    )
    await ConfigAdapter().update_config(
        token, event["id"], f"{MODE}_VIDEO_SERVICE_AVAILABLE", "False"
    )
    logging.info("Goodbye!")


async def run_the_video_service(token: str, event: dict, status_type: str, instance_name: str) -> None:
    """Run the service."""
    video_config = {}
    video_config = await get_config(token, event["id"], MODE)
    storage_mode = await ConfigAdapter().get_config(
        token, event["id"], "VIDEO_STORAGE_MODE"
    )

    try:
        if video_config["video_start"]:
            if MODE == "CAPTURE_LOCAL":
                await VisionAIService().print_photo_with_trigger_line(token, event, status_type)
                await VideoService().capture_video(
                    token, event, status_type, instance_name
                )
            elif MODE == "CAPTURE_SRT":
                await run_capture_srt(token, event, status_type, instance_name)
            elif MODE == "DETECT":
                if storage_mode == "cloud_storage":
                    await VideoService().detect_crossings_cloud_storage(token, event, instance_name, status_type)
                else:
                    await VideoService().detect_crossings_local_storage(token, event, status_type)
        elif video_config["video_running"]:
            # should be invalid (no muliti thread) - reset
            await ConfigAdapter().update_config(
                token, event["id"], f"{MODE}_VIDEO_SERVICE_RUNNING", "False"
            )
        elif video_config["new_trigger_line_photo"] and MODE == "CAPTURE_LOCAL":
            # new trigger line photo - reset
            await VisionAIService().print_photo_with_trigger_line(token, event, status_type)

    except Exception as e:
        err_string = str(e)
        logging.exception(err_string)
        await StatusAdapter().create_status(
            token,
            event,
            status_type,
            f"Error in {instance_name}. Stopping.",
            {"error": err_string},
        )
        await ConfigAdapter().update_config(
            token, event["id"], f"{MODE}_VIDEO_SERVICE_RUNNING", "False"
        )
        await ConfigAdapter().update_config(
            token, event["id"], f"{MODE}_VIDEO_SERVICE_START", "False"
        )

async def do_login() -> str:
    """Login to data-source."""
    uid = os.getenv("ADMIN_USERNAME", "a")
    pw = os.getenv("ADMIN_PASSWORD", ".")
    while True:
        try:
            token = await UserAdapter().login(uid, pw)
            if token:
                return token
        except Exception as e:
            err_string = str(e)
            logging.info(err_string)
        logging.info("video-service is waiting for db connection")
        await asyncio.sleep(5)


async def get_event(token: str) -> dict:
    """Get event_details - use info from config and db."""
    def raise_multiple_events_error(events_db: list) -> None:
        """Raise an exception for multiple events found."""
        information = (
            f"Multiple events found. Please specify an EVENT_ID in .env: {events_db}"
        )
        raise Exception(information)

    event = {}
    while True:
        try:
            events_db = await EventsAdapter().get_all_events(token)
            event_id_config = os.getenv("EVENT_ID")
            if len(events_db) == 1:
                event = events_db[0]
            elif len(events_db) > 1:
                for _event in events_db:
                    if _event["id"] == event_id_config:
                        event = _event
                        break
                else:
                    raise_multiple_events_error(events_db)
            if event:
                break
        except Exception as e:
            err_string = str(e)
            logging.info(err_string)
        logging.info("video-service is waiting for an event to work on.")
        await asyncio.sleep(5)

    return event


async def get_config(token: str, event_id: str, mode: str) -> dict:
    """Get config details - use info from db."""
    video_running = await ConfigAdapter().get_config_bool(
        token, event_id, f"{mode}_VIDEO_SERVICE_RUNNING"
    )
    video_start = await ConfigAdapter().get_config_bool(
        token, event_id, f"{mode}_VIDEO_SERVICE_START"
    )
    new_trigger_line_photo = await ConfigAdapter().get_config_bool(
        token, event_id, "NEW_TRIGGER_LINE_PHOTO"
    )
    return {
        "video_running": video_running,
        "video_start": video_start,
        "new_trigger_line_photo": new_trigger_line_photo,
    }


async def run_capture_srt(token: str, event: dict, status_type: str, instance_name: str) -> None:
    """Run SRT Push video capture using Google Live Stream API.
    
    This function creates a Live Stream API channel that waits for incoming SRT Push streams
    and stores the video directly to cloud storage with configurable clip duration.
    
    Args:
        token: Authentication token for database access
        event: Event details including event ID
        status_type: Status type for logging
        instance_name: Name of the service instance
        
    Raises:
        Exception: If video-streaming module is not available
    """
    if not LIVESTREAM_AVAILABLE:
        error_msg = "video-streaming module not available. Install with: pip install google-cloud-video-live-stream"
        logging.error(error_msg)
        await StatusAdapter().create_status(
            token, event, status_type, "CAPTURE_SRT requires video-streaming module", 
            {"error": error_msg}
        )
        raise Exception(error_msg)
    
    # Get clip duration from config
    clip_duration = await ConfigAdapter().get_config_int(
        token, event["id"], "VIDEO_CLIP_DURATION"
    )
    
    try:
        # Initialize Live Stream service
        service = LiveStreamService()
        
        # Create and start the channel
        logging.info("Creating Live Stream API channel for event: %s", event["id"])
        channel_info = await service.create_and_start_channel(
            event_id=event["id"],
            clip_duration=clip_duration,
        )
        
        # Update status with SRT Push URL
        srt_push_url = channel_info["srt_push_url"]
        output_uri = channel_info["output_uri"]
        
        informasjon = f"SRT Push channel ready. Stream to: {srt_push_url}"
        await StatusAdapter().create_status(
            token,
            event,
            status_type,
            informasjon,
            {
                "instance_name": instance_name,
                "srt_push_url": srt_push_url,
                "output_uri": output_uri,
                "segment_duration": clip_duration,
            },
        )
        
        logging.info("Channel created. Waiting for SRT Push stream at: %s", srt_push_url)
        logging.info("Video will be stored to: %s", output_uri)
        
        # Keep the channel running while VIDEO_SERVICE_START is True
        while True:
            continue_streaming = await ConfigAdapter().get_config_bool(
                token, event["id"], "CAPTURE_SRT_VIDEO_SERVICE_START"
            )
            
            if not continue_streaming:
                logging.info("Stopping SRT capture for event: %s", event["id"])
                break
            
            # Check channel status periodically
            try:
                status = await service.get_channel_status(event_id=event["id"])
                logging.debug("Channel status: %s", status["state"])
            except Exception as e:
                logging.warning("Failed to get channel status: %s", e)
            
            await asyncio.sleep(10)
        
        # Stop and cleanup the channel
        logging.info("Stopping Live Stream channel for event: %s", event["id"])
        await service.stop_channel(event_id=event["id"])
        
        informasjon = "SRT Push channel stopped. Cleaning up resources."
        await StatusAdapter().create_status(
            token, event, status_type, informasjon, 
            {"instance_name": instance_name}
        )
        
        await service.cleanup_resources(event_id=event["id"])
        
        informasjon = f"SRT capture completed. Videos stored in: {output_uri}"
        await StatusAdapter().create_status(
            token, event, status_type, informasjon,
            {"instance_name": instance_name, "output_uri": output_uri}
        )
        
    except Exception as e:
        err_string = str(e)
        logging.exception("Error in SRT capture: %s", err_string)
        
        # Try to cleanup on error
        try:
            if LIVESTREAM_AVAILABLE:
                service = LiveStreamService()
                await service.cleanup_resources(event_id=event["id"])
        except Exception:
            logging.exception("Failed to cleanup Live Stream resources after error")
        
        raise


if __name__ == "__main__":
    asyncio.run(main())
