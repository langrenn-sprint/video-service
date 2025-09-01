"""Module for events adapter."""

import datetime
import logging
import os
from http import HTTPStatus
from zoneinfo import ZoneInfo

from aiohttp import ClientSession, hdrs
from multidict import MultiDict

# get base settings
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

    def get_local_datetime_now(self, event: dict) -> datetime.datetime:
        """Return local datetime object, time zone adjusted from event info."""
        time_zone = event["timezone"]
        if time_zone:
            local_time_obj = datetime.datetime.now(ZoneInfo(time_zone))
        else:
            local_time_obj = datetime.datetime.now(datetime.UTC)
        return local_time_obj

    def get_local_time(self, event: dict, time_format: str) -> str:
        """Return local time string, time zone adjusted from event info."""
        local_time = ""
        time_zone = event["timezone"]
        time_now = datetime.datetime.now(ZoneInfo(time_zone)) if time_zone else datetime.datetime.now(datetime.UTC)

        if time_format == "HH:MM":
            local_time = f"{time_now.strftime('%H')}:{time_now.strftime('%M')}"
        elif time_format == "log":
            local_time = f"{time_now.strftime('%Y')}-{time_now.strftime('%m')}-{time_now.strftime('%d')}T{time_now.strftime('%X')}"
        else:
            local_time = time_now.strftime("%X")
        return local_time
