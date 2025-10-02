"""Module for application looking at video and detecting line crossings."""

import asyncio
import logging
import os
from logging.handlers import RotatingFileHandler

from video_service.adapters import (
    ConfigAdapter,
    EventsAdapter,
    PhotosFileAdapter,
    StatusAdapter,
    UserAdapter,
)
from video_service.services import VideoService, VisionAIService

# get base settings
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
PhotosFileAdapter().init_video_folder(MODE)

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

            if MODE not in ["CAPTURE", "FILTER", "DETECT"]:
                informasjon = f"Invalid mode {MODE} - no video processing will be done."
                raise Exception(informasjon)

            information = (
                f"video-service is ready, mode {MODE}! - {event['name']}, {event['date_of_event']}"
            )
            status_type = await ConfigAdapter().get_config(
                token, event["id"], "VIDEO_SERVICE_STATUS_TYPE"
            )
            await StatusAdapter().create_status(
                token, event, status_type, information
            )
            # service ready!
            await ConfigAdapter().update_config(
                token, event["id"], f"{MODE}_VIDEO_SERVICE_AVAILABLE", "True"
            )

            i = 0
            while True:
                if i > STATUS_INTERVAL:
                    informasjon = f"video-service er klar, mode {MODE}."
                    await StatusAdapter().create_status(
                        token, event, status_type, informasjon
                    )
                    i = 0
                else:
                    i += 1
                await run_the_video_service(token, event, status_type)
                await asyncio.sleep(5)

        except Exception as e:
            err_string = str(e)
            logging.exception(err_string)
            await StatusAdapter().create_status(
                token, event, status_type, f"Critical Error - exiting program: {err_string}"
            )
    except asyncio.CancelledError:
        await ConfigAdapter().update_config(
            token, event["id"], f"{MODE}_VIDEO_SERVICE_AVAILABLE", "False"
        )
        await ConfigAdapter().update_config(
            token, event["id"], f"{MODE}_VIDEO_SERVICE_RUNNING", "False"
        )
        await StatusAdapter().create_status(
            token, event, status_type, f"video-service {MODE} was cancelled (ctrl-c pressed)."
        )
        raise
    await ConfigAdapter().update_config(
        token, event["id"], f"{MODE}_VIDEO_SERVICE_AVAILABLE", "False"
    )
    logging.info("Goodbye!")


async def run_the_video_service(token: str, event: dict, status_type: str) -> None:
    """Run the service."""
    video_config = {}
    video_config = await get_config(token, event["id"], MODE)
    storage_mode = await ConfigAdapter().get_config(
        token, event["id"], "VIDEO_STORAGE_MODE"
    )

    try:
        if video_config["video_start"]:
            if MODE == "CAPTURE":
                await VisionAIService().print_photo_with_trigger_line(token, event, status_type)
                await VideoService().capture_video(
                    token, event, status_type
                )
            elif MODE == "FILTER":
                await VideoService().filter_video(
                    token, event, status_type, storage_mode
                )
            elif MODE == "DETECT":
                await VideoService().detect_crossings(
                    token, event
                )
        elif video_config["video_running"]:
            # should be invalid (no muliti thread) - reset
            await ConfigAdapter().update_config(
                token, event["id"], f"{MODE}_VIDEO_SERVICE_RUNNING", "False"
            )
        elif video_config["new_trigger_line_photo"] and MODE == "CAPTURE":
            # new trigger line photo - reset
            await VisionAIService().print_photo_with_trigger_line(token, event, status_type)

    except Exception as e:
        err_string = str(e)
        logging.exception(err_string)
        await StatusAdapter().create_status(
            token,
            event,
            status_type,
            f"Error in video-service: {err_string}",
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


if __name__ == "__main__":
    asyncio.run(main())
