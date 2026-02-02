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
    ServiceInstanceAdapter,
    StatusAdapter,
    UserAdapter,
)
from video_service.services import LiveStreamService, VideoService, VisionAIService

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

# Generate from hostname and PID
service_info = {
    "mode": os.getenv("MODE", "DUMMY"),
    "name": "",
    "id": "",
    "status_type": "",
}

if os.getenv("K_REVISION"):
    service_info["name"] = str(os.getenv("K_REVISION"))
else:
    service_info["name"] = f"{socket.gethostname()}"


async def create_service_instance_dict(
    token: str,
    event: dict,
) -> dict:
    """Create a service instance dictionary.

    Args:
        token: Authentication token for database access
        event: The event dictionary

    Returns:
        A dictionary representing the service instance

    """
    time_now = EventsAdapter().get_local_time(event, "log")
    return {
        "service_type": f"VIDEO_SERVICE_{service_info['mode']}",
        "instance_name": service_info["name"],
        "status": "ready",
        "host_name": socket.gethostname(),
        "action": "",
        "event_id": event["id"],
        "started_at": time_now,
        "last_heartbeat": time_now,
        "metadata": {
            "latest_photo_url": "",
            "trigger_line_xyxyn": await ConfigAdapter().get_config(
                token, event["id"], "TRIGGER_LINE_XYXYN"
            ),
        }
    }


async def main() -> None:
    """CLI for analysing video stream."""
    token = ""
    event = {}
    try:
        try:
            # login to data-source
            token = await do_login()
            event = await get_event(token)

            if service_info["mode"] not in ["CAPTURE_LOCAL", "CAPTURE_SRT", "DETECT"]:
                informasjon = f"Invalid mode {service_info['mode']} - exiting."
                raise Exception(informasjon)

            service_info["status_type"] += await ConfigAdapter().get_config(
                token, event["id"], "VIDEO_SERVICE_STATUS_TYPE"
            ) + f"_{service_info['mode']}"
            information = (f"{service_info['name']}, mode {service_info['mode']} er klar.")
            await StatusAdapter().create_status(
                token, event, service_info["status_type"], information, event
            )

            service_instance = await create_service_instance_dict(token, event)
            service_info["id"] = await ServiceInstanceAdapter().create_service_instance(token, service_instance)

            i = 0
            while True:
                try:
                    if i > STATUS_INTERVAL:
                        await ServiceInstanceAdapter().send_heartbeat(token, event, service_info["id"])
                        i = 0
                    else:
                        i += 1
                    await run_the_video_service(token, event, service_info)
                    # service ready!
                    await ServiceInstanceAdapter().update_service_instance_status(token, event, service_info["id"], "ready")
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
                token, event, service_info["status_type"], "Critical Error - exiting program", {"error": err_string}
            )
            if service_info["id"]:
                await ServiceInstanceAdapter().delete_service_instance(
                    token, service_info["id"]
                )
    except asyncio.CancelledError:
        await StatusAdapter().create_status(
            token,
            event,
            service_info["status_type"],
            f"{service_info['name']} was cancelled (ctrl-c pressed).",
            {}
        )
    if service_info["id"]:
        await ServiceInstanceAdapter().delete_service_instance(token, service_info["id"])
    logging.info("Goodbye!")


async def run_the_video_service(token: str, event: dict, service_info: dict) -> None:
    """Run the service."""
    video_config = {}
    video_config = await get_config(token, service_info["id"])
    storage_mode = await ConfigAdapter().get_config(
        token, event["id"], "VIDEO_STORAGE_MODE"
    )

    try:
        if video_config["video_start"]:
            await ServiceInstanceAdapter().update_service_instance_status(
                token, event, service_info["id"], "running"
            )
            if service_info["mode"] == "CAPTURE_LOCAL":
                await VisionAIService().print_photo_with_trigger_line(token, event, service_info["status_type"])
                await VideoService().capture_video(token, event, service_info)
            elif service_info["mode"] == "CAPTURE_SRT":
                await VisionAIService().print_photo_with_trigger_line(token, event, service_info["status_type"])
                await run_capture_srt(token, event, service_info)
            elif service_info["mode"] == "DETECT":
                if storage_mode == "local_storage":
                    await VideoService().detect_crossings_local_storage(token, event, service_info["status_type"])
                else:
                    await VideoService().detect_crossings_cloud_storage(
                        token, event, service_info["name"], service_info["status_type"]
                    )
        elif video_config["new_trigger_line_photo"]:
            # new trigger line photo - reset
            await VisionAIService().print_photo_with_trigger_line(token, event, service_info["status_type"])

    except Exception as e:
        err_string = str(e)
        logging.exception(err_string)
        await StatusAdapter().create_status(
            token,
            event,
            service_info["status_type"],
            f"Error in {service_info['name']}.",
            {"error": err_string},
        )
        await ServiceInstanceAdapter().update_service_instance_action(token, event, service_info["id"], "error")

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
            "Multiple events found. Please specify an EVENT_ID in .env: "
        )
        for _event in events_db:
            information += f"\n *** {_event['name']}, {_event['date_of_event']} id: {_event['id']} "
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


async def get_config(token: str, instance_id: str) -> dict:
    """Get config details - use info from db."""
    instance_info = await ServiceInstanceAdapter().get_service_instance_by_id(token, instance_id)
    instance_config = {
        "video_start": False,
        "new_trigger_line_photo": False,
    }

    if instance_info["action"] == "start":
        instance_config["video_start"] = True
    elif instance_info["action"] == "trigger_line_photo":
        instance_config["new_trigger_line_photo"] = True
    elif instance_info["action"] == "stop":
        instance_config["video_start"] = False

    return instance_config


async def run_capture_srt(token: str, event: dict, service_info: dict) -> None:
    """Run SRT Push video capture using Google Live Stream API.

    This function creates a Live Stream API channel that waits for incoming SRT Push streams
    and stores the video directly to cloud storage with configurable clip duration.

    Args:
        token: Authentication token for database access
        event: Event details including event ID
        service_info: Information about the service instance

    Raises:
        Exception: If video-streaming module is not available

    """
    try:
        # Initialize Live Stream service
        service = LiveStreamService()

        # Create and start the channel
        logging.info("Creating Live Stream API channel for event: %s", event["id"])
        channel_info = await service.create_and_start_channel(
            token,
            event,
        )

        # Update status with SRT Push URL
        srt_push_url = channel_info["srt_push_url"]
        output_uri = channel_info["output_uri"]

        logging.info("Channel created. Waiting for SRT Push stream at: %s", srt_push_url)
        logging.info("Video will be stored to: %s", output_uri)

        # Keep the channel running while VIDEO_SERVICE_START is True
        while True:
            instance_info = await ServiceInstanceAdapter().get_service_instance_by_id(token, service_info["id"])

            if instance_info["action"] == "stop":
                logging.info("Stopping SRT capture for event: %s", event["id"])
                break

            # Check channel status periodically
            try:
                status = await service.get_channel_status(token, event)
                logging.debug("Channel status: %s", status["state"])
            except Exception as e:
                logging.warning("Failed to get channel status: %s", e)

            await asyncio.sleep(10)

        # Stop and cleanup the channel
        logging.info("Stopping Live Stream channel for event: %s", event["id"])
        await service.stop_channel(token, event)

        informasjon = "SRT Push channel stopped. Cleaning up resources."
        await StatusAdapter().create_status(
            token, event, service_info["status_type"], informasjon,
            {"service_info": service_info}
        )

        await service.cleanup_resources(token, event)

        informasjon = f"SRT capture completed. Videos stored in: {output_uri}"
        await StatusAdapter().create_status(
            token, event, service_info["status_type"], informasjon,
            {"service_info": service_info, "output_uri": output_uri}
        )

    except Exception as e:
        err_string = str(e)
        logging.exception("Error in SRT capture: %s", err_string)


if __name__ == "__main__":
    asyncio.run(main())
