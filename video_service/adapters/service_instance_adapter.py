"""Module for service instance adapter."""

import logging
import os
from http import HTTPStatus

from aiohttp import ClientSession, hdrs, web
from multidict import MultiDict

from .events_adapter import (
    EventsAdapter,
)

PHOTOS_HOST_SERVER = os.getenv("PHOTOS_HOST_SERVER", "localhost")
PHOTOS_HOST_PORT = os.getenv("PHOTOS_HOST_PORT", "8092")
PHOTO_SERVICE_URL = f"http://{PHOTOS_HOST_SERVER}:{PHOTOS_HOST_PORT}"


class ServiceInstanceAdapter:

    """Class representing service instance."""

    async def get_all_service_instances(
        self,
        token: str,
        event_id: str | None = None,
        service_type: str | None = None,
        status: str | None = None,
    ) -> list:
        """Get all service instances function."""
        service_instances = []
        headers = MultiDict(
            [
                (hdrs.CONTENT_TYPE, "application/json"),
                (hdrs.AUTHORIZATION, f"Bearer {token}"),
            ],
        )
        servicename = "get_all_service_instances"

        # Build URL with query parameters
        query_params = []
        if event_id:
            query_params.append(f"eventId={event_id}")
        if service_type:
            query_params.append(f"serviceType={service_type}")
        if status:
            query_params.append(f"status={status}")

        url = f"{PHOTO_SERVICE_URL}/service-instances"
        if query_params:
            url += "?" + "&".join(query_params)

        async with ClientSession() as session, session.get(
            url,
            headers=headers,
        ) as resp:
            if resp.status == HTTPStatus.OK:
                service_instances = await resp.json()
            elif resp.status == HTTPStatus.UNAUTHORIZED:
                informasjon = f"Login expired: {resp}"
                raise Exception(informasjon)
            else:
                body = await resp.json()
                informasjon = f"{servicename} failed - {resp.status} - {body['detail']}"
                logging.error(informasjon)
                raise web.HTTPBadRequest(reason=informasjon)
        return service_instances

    async def get_service_instance_by_id(
        self,
        token: str,
        service_instance_id: str,
    ) -> dict:
        """Get a service instance by id."""
        service_instance = {}
        headers = MultiDict(
            [
                (hdrs.CONTENT_TYPE, "application/json"),
                (hdrs.AUTHORIZATION, f"Bearer {token}"),
            ],
        )
        servicename = "get_service_instance_by_id"

        async with ClientSession() as session, session.get(
            f"{PHOTO_SERVICE_URL}/service-instances/{service_instance_id}",
            headers=headers,
        ) as resp:
            if resp.status == HTTPStatus.OK:
                service_instance = await resp.json()
            elif resp.status == HTTPStatus.NOT_FOUND:
                informasjon = (
                    f"Service instance with id {service_instance_id} not found"
                )
                logging.error(informasjon)
                raise web.HTTPNotFound(reason=informasjon)
            elif resp.status == HTTPStatus.UNAUTHORIZED:
                informasjon = f"Login expired: {resp}"
                raise Exception(informasjon)
            else:
                body = await resp.json()
                informasjon = f"{servicename} failed - {resp.status} - {body['detail']}"
                logging.error(informasjon)
                raise web.HTTPBadRequest(reason=informasjon)
        return service_instance

    async def create_service_instance(
        self,
        token: str,
        service_instance: dict,
    ) -> str:
        """Create new service instance function."""
        servicename = "create_service_instance"
        result = ""
        headers = MultiDict(
            [
                (hdrs.CONTENT_TYPE, "application/json"),
                (hdrs.AUTHORIZATION, f"Bearer {token}"),
            ],
        )

        async with ClientSession() as session, session.post(
            f"{PHOTO_SERVICE_URL}/service-instances",
            headers=headers,
            json=service_instance,
        ) as resp:
            if resp.status == HTTPStatus.CREATED:
                logging.debug(f"result - got response {resp}")
                location = resp.headers[hdrs.LOCATION]
                result = location.split(os.path.sep)[-1]
            elif resp.status == HTTPStatus.UNAUTHORIZED:
                informasjon = f"Login expired: {resp}"
                raise Exception(informasjon)
            elif resp.status == HTTPStatus.UNPROCESSABLE_ENTITY:
                body = await resp.json()
                informasjon = (
                    f"{servicename} failed - {resp.status} - {body['detail']}"
                )
                logging.error(informasjon)
                raise web.HTTPUnprocessableEntity(reason=informasjon)
            else:
                body = await resp.json()
                informasjon = f"{servicename} failed - {resp.status} - {body['detail']}"
                logging.error(informasjon)
                raise web.HTTPBadRequest(reason=informasjon)

        return result


    async def update_service_instance_action(
        self,
        token: str,
        event: dict,
        instance_id: str,
        action: str,
    ) -> str:
        """Update service instance action function."""
        informasjon = ""
        service_instances = []

        if instance_id:
            service_instances.append(
                await self.get_service_instance_by_id(token, instance_id),
            )
        elif action in ["start_all", "stop_all"]:
            service_instances = await self.get_all_service_instances(
                token,
                event_id=event["id"],
            )
            action = action.replace("_all", "")

        for instance in service_instances:
            # Update the service instance
            instance["action"] = action
            instance["last_updated"] = EventsAdapter().get_local_time(event, "log")
            informasjon = await self.update_service_instance(
                token, instance["id"], instance,
            )
        return informasjon


    async def update_service_instance_status(
        self,
        token: str,
        event: dict,
        instance_id: str,
        status: str,
    ) -> str:
        """Update service instance status function."""
        informasjon = ""
        service_instances = []

        if instance_id:
            service_instances.append(
                await self.get_service_instance_by_id(token, instance_id),
            )
        for instance in service_instances:
            # Update the service instance
            instance["status"] = status
            instance["last_updated"] = EventsAdapter().get_local_time(event, "log")
            informasjon = await self.update_service_instance(
                token, instance["id"], instance,
            )
        return informasjon


    async def send_heartbeat(
        self,
        token: str,
        event: dict,
        instance_id: str,
    ) -> str:
        """Update service instance function."""
        # Get the current service instance and update the last_heartbeat field
        instance = await self.get_service_instance_by_id(token, instance_id)
        instance["last_heartbeat"] = EventsAdapter().get_local_time(event, "log")

        # Update the service instance
        return await self.update_service_instance(token, instance_id, instance)

    async def update_service_instance(
        self,
        token: str,
        service_instance_id: str,
        service_instance: dict,
    ) -> str:
        """Update service instance function."""
        response = ""
        servicename = "update_service_instance"
        headers = MultiDict(
            [
                (hdrs.CONTENT_TYPE, "application/json"),
                (hdrs.AUTHORIZATION, f"Bearer {token}"),
            ],
        )

        async with ClientSession() as session, session.put(
            f"{PHOTO_SERVICE_URL}/service-instances/{service_instance_id}",
            headers=headers,
            json=service_instance,
        ) as resp:
            response = str(resp.status)
            if resp.status == HTTPStatus.NO_CONTENT:
                logging.debug(f"update service instance - got response {resp}")
            elif resp.status == HTTPStatus.NOT_FOUND:
                informasjon = (
                    f"Service instance with id {service_instance_id} not found"
                )
                logging.error(informasjon)
                raise web.HTTPNotFound(reason=informasjon)
            elif resp.status == HTTPStatus.UNAUTHORIZED:
                informasjon = f"Login expired: {resp}"
                raise Exception(informasjon)
            elif resp.status == HTTPStatus.UNPROCESSABLE_ENTITY:
                body = await resp.json()
                informasjon = (
                    f"{servicename} failed - {resp.status} - {body['detail']}"
                )
                logging.error(informasjon)
                raise web.HTTPUnprocessableEntity(reason=informasjon)
            else:
                body = await resp.json()
                informasjon = f"{servicename} failed - {resp.status} - {body['detail']}"
                logging.error(informasjon)
                raise web.HTTPBadRequest(reason=informasjon)
        return response

    async def delete_service_instance(
        self,
        token: str,
        service_instance_id: str,
    ) -> str:
        """Delete service instance function."""
        response = ""
        servicename = "delete_service_instance"
        headers = MultiDict(
            [
                (hdrs.CONTENT_TYPE, "application/json"),
                (hdrs.AUTHORIZATION, f"Bearer {token}"),
            ],
        )

        async with ClientSession() as session, session.delete(
            f"{PHOTO_SERVICE_URL}/service-instances/{service_instance_id}",
            headers=headers,
        ) as resp:
            response = str(resp.status)
            if resp.status == HTTPStatus.NO_CONTENT:
                logging.debug(f"delete service instance - got response {resp}")
            elif resp.status == HTTPStatus.NOT_FOUND:
                informasjon = (
                    f"Service instance with id {service_instance_id} not found"
                )
                logging.error(informasjon)
                raise web.HTTPNotFound(reason=informasjon)
            elif resp.status == HTTPStatus.UNAUTHORIZED:
                informasjon = f"Login expired: {resp}"
                raise Exception(informasjon)
            else:
                body = await resp.json()
                informasjon = f"{servicename} failed - {resp.status} - {body['detail']}"
                logging.error(informasjon)
                raise web.HTTPBadRequest(reason=informasjon)
        return response
