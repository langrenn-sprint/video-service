"""Module for user adapter."""

import logging
import os
from http import HTTPStatus

from aiohttp import ClientSession, hdrs
from dotenv import load_dotenv
from multidict import MultiDict

# get base settings
load_dotenv()
USERS_HOST_SERVER = os.getenv("USERS_HOST_SERVER")
USERS_HOST_PORT = os.getenv("USERS_HOST_PORT")
USER_SERVICE_URL = f"http://{USERS_HOST_SERVER}:{USERS_HOST_PORT}"


class UserAdapter:
    """Class representing user."""

    async def login(self, username: str, password: str) -> str:
        """Perform login function, return token."""
        result = 0
        request_body = {
            "username": username,
            "password": password,
        }
        headers = MultiDict(
            [
                (hdrs.CONTENT_TYPE, "application/json"),
            ]
        )
        async with ClientSession() as session, session.post(
            f"{USER_SERVICE_URL}/login", headers=headers, json=request_body
        ) as resp:
            result = resp.status
            logging.info(f"do login - got response {result}")
            if result == HTTPStatus.OK:
                body = await resp.json()
                return body["token"]
        return ""
