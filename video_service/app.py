"""Module for application looking at video and detecting line crossings."""

import asyncio
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

from video_service.adapters import (
    ConfigAdapter,
    EventsAdapter,
    StatusAdapter,
    UserAdapter,
)
from video_service.services import VideoService

# get base settings
load_dotenv()
CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}
video_file_path = f"{Path.cwd()}/video_service/files"
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


async def main() -> None:
    """CLI for analysing video stream."""
    token = ""
    event = {}
    status_type = ""
    i = STATUS_INTERVAL
    try:
        # login to data-source
        token = await do_login()
        event = await get_event(token)
        information = (
            f"video-service is ready! - {event['name']}, {event['date_of_event']}"
        )
        status_type = await ConfigAdapter().get_config(
            token, event["id"], "VIDEO_SERVICE_STATUS_TYPE"
        )
        await StatusAdapter().create_status(
            token, event, status_type, information
        )

        # service ready!
        await ConfigAdapter().update_config(
            token, event["id"], "VIDEO_SERVICE_AVAILABLE", "True"
        )
        while True:
            video_config = await get_config(token, event["id"])
            try:
                if video_config["stop_tracking"]:
                    await ConfigAdapter().update_config(
                        token, event["id"], "VIDEO_SERVICE_STOP", "False"
                    )
                elif video_config["video_start"]:
                    await VideoService().capture_video(
                        token, event, status_type, video_file_path
                    )
                elif video_config["video_running"]:
                    # should be invalid (no muliti thread) - reset
                    await ConfigAdapter().update_config(
                        token, event["id"], "VIDEO_SERVICE_RUNNING", "False"
                    )
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
                    token, event["id"], "VIDEO_SERVICE_RUNNING", "False"
                )
                await ConfigAdapter().update_config(
                    token, event["id"], "VIDEO_SERVICE_START", "False"
                )
            if i > STATUS_INTERVAL:
                informasjon = "video-service er klar til å starte analyse."
                await StatusAdapter().create_status(
                    token, event, status_type, informasjon
                )
                i = 0
            else:
                i += 1
            await asyncio.sleep(2)
    except Exception as e:
        err_string = str(e)
        logging.exception(err_string)
        await StatusAdapter().create_status(
            token, event, status_type, f"Critical Error - exiting program: {err_string}"
        )
    await ConfigAdapter().update_config(
        token, event["id"], "VIDEO_SERVICE_AVAILABLE", "False"
    )
    logging.info("Goodbye!")


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


async def get_config(token: str, event_id: str) -> dict:
    """Get config details - use info from db."""
    video_running = await ConfigAdapter().get_config_bool(
        token, event_id, "VIDEO_SERVICE_RUNNING"
    )
    video_start = await ConfigAdapter().get_config_bool(
        token, event_id, "VIDEO_SERVICE_START"
    )
    stop_tracking = await ConfigAdapter().get_config_bool(
        token, event_id, "VIDEO_SERVICE_STOP"
    )
    start_simulation = await ConfigAdapter().get_config_bool(
        token, event_id, "SIMULATION_CROSSINGS_START"
    )
    draw_trigger_line = await ConfigAdapter().get_config_bool(
        token, event_id, "DRAW_TRIGGER_LINE"
    )
    return {
        "video_running": video_running,
        "video_start": video_start,
        "start_simulation": start_simulation,
        "stop_tracking": stop_tracking,
        "draw_trigger_line": draw_trigger_line,
    }


if __name__ == "__main__":
    asyncio.run(main())
