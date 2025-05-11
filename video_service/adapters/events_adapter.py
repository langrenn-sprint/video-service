"""Module for events adapter."""

import logging
import os
from datetime import datetime
from http import HTTPStatus
from zoneinfo import ZoneInfo

from aiohttp import ClientSession, hdrs
from dotenv import load_dotenv
from multidict import MultiDict

# get base settings
load_dotenv()
EVENTS_HOST_SERVER = os.getenv("EVENTS_HOST_SERVER", "localhost")
EVENTS_HOST_PORT = os.getenv("EVENTS_HOST_PORT", "8082")
EVENT_SERVICE_URL = f"http://{EVENTS_HOST_SERVER}:{EVENTS_HOST_PORT}"


class EventsAdapter:
    """Class representing events."""

    async def get_all_events(self, token: str) -> list:
        """Get all events function."""
        events = []
        headers = MultiDict(
            [
                (hdrs.CONTENT_TYPE, "application/json"),
                (hdrs.AUTHORIZATION, f"Bearer {token}"),
            ]
        )

        async with ClientSession() as session, session.get(
                f"{EVENT_SERVICE_URL}/events", headers=headers
            ) as resp:
                logging.debug(f"get_all_events - got response {resp.status}")
                if resp.status == HTTPStatus.OK:
                    events = await resp.json()
                    logging.debug(f"events - got response {events}")
                elif resp.status == HTTPStatus.UNAUTHORIZED:
                    informasjon = f"Login expired: {resp}"
                    raise Exception(informasjon)
                else:
                    informasjon = f"Error {resp.status} getting events: {resp} "
                    logging.error(informasjon)
        return events

    def get_local_datetime_now(self, event: dict) -> datetime:
        """Return local datetime object, time zone adjusted from event info."""
        timezone = event["timezone"]
        return datetime.now(ZoneInfo(timezone)) if timezone else datetime.now(timezone.utc)

    def get_local_time(self, event: dict, time_format: str) -> str:
        """Return local time string, time zone adjusted from event info."""
        local_time = ""
        timezone = event["timezone"]
        t_n = datetime.now(ZoneInfo(timezone)) if timezone else datetime.now(timezone.utc)
        if time_format == "HH:MM":
            local_time = f"{t_n.strftime('%H')}:{t_n.strftime('%M')}"
        elif time_format == "log":
            local_day = (
                f"{t_n.strftime('%Y')}-{t_n.strftime('%m')}-{t_n.strftime('%d')}"
            )
            local_time = f"{local_day}T{t_n.strftime('%X')}"
        else:
            local_time = t_n.strftime("%X")
        return local_time
