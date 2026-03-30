"""
PhishLabs feed API client.

HTTP integration with https://feed.phishlabs.com (createincident, incident.get).
"""

import logging
from typing import Any, Dict, Literal, Optional

import aiohttp
from fastapi import HTTPException

logger = logging.getLogger(__name__)

PhishLabsAction = Literal["check", "create"]


class PhishLabsAPIClient:
    """Client for PhishLabs feed API operations."""

    BASE_URL = "https://feed.phishlabs.com"

    def __init__(self) -> None:
        self.session: Optional[aiohttp.ClientSession] = None
        self._connector: Optional[aiohttp.TCPConnector] = None

    async def __aenter__(self) -> "PhishLabsAPIClient":
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.shutdown()

    async def initialize(self) -> None:
        if self.session is None or self.session.closed:
            if self._connector is None or self._connector.closed:
                self._connector = aiohttp.TCPConnector(
                    limit=10,
                    limit_per_host=5,
                    keepalive_timeout=30,
                    enable_cleanup_closed=True,
                )
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            self.session = aiohttp.ClientSession(
                connector=self._connector,
                timeout=timeout,
            )
            logger.debug("Initialized PhishLabs API client session")

    async def shutdown(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
        if self._connector and not self._connector.closed:
            await self._connector.close()
            self._connector = None
        logger.debug("PhishLabs API client session closed")

    async def call_createincident_flow(
        self,
        url: str,
        api_key: str,
        catcode: str = "12345",
        action: PhishLabsAction = "check",
    ) -> Dict[str, Any]:
        """
        Call PhishLabs createincident then incident.get when an incident id exists.

        Args:
            url: Domain / URL string sent as the API `url` query parameter.
            api_key: PhishLabs custid API key.
            catcode: Category code (default 12345 for check).
            action: "check" (flags=2) or "create" (flags=0).

        Returns:
            Dict with API responses and incident metadata.

        Raises:
            HTTPException: Same status codes/messages as the legacy route helper.
        """
        await self.initialize()
        assert self.session is not None

        if action == "create":
            flags = 0
            final_catcode = catcode if catcode else "12345"
            if final_catcode == "12345":
                raise HTTPException(
                    status_code=400,
                    detail="Valid catcode required for creating incidents (cannot use default 12345)",
                )
            comment = "Typosquat domain that impersonate our Brand. Please monitor."
        else:
            flags = 2
            final_catcode = "12345"

        if hasattr(url, "__class__") and "Url" in str(type(url)):
            url = str(url)
        elif not isinstance(url, str):
            url = str(url)

        logger.debug("Using url for PhishLabs API: %s (type: %s)", url, type(url))

        createincident_url = (
            f"{self.BASE_URL}/createincident"
            f"?custid={api_key}"
            "&requestid=placeholder"
            f"&url={url}"
            f"&catcode={final_catcode}"
            f"&flags={flags}"
        )
        if action == "create":
            createincident_url += f"&comment={comment}"

        request_timeout = aiohttp.ClientTimeout(total=30)

        async with self.session.get(createincident_url, timeout=request_timeout) as resp:
            if resp.status != 200:
                body_text = await resp.text()
                raise HTTPException(
                    status_code=502,
                    detail=f"PhishLabs createincident error {resp.status}: {body_text[:1000]}",
                )
            createincident_response = await resp.json(content_type=None)

        if createincident_response is None:
            raise HTTPException(
                status_code=502,
                detail="Empty response from PhishLabs createincident call",
            )

        incident_id = createincident_response.get("IncidentId")
        error_message = createincident_response.get("ErrorMessage")
        logger.debug("Phishlabs Incident ID: %s", incident_id)
        if error_message:
            raise HTTPException(status_code=400, detail=f"PhishLabs error: {error_message}")

        if not incident_id:
            return {
                "createincident_response": createincident_response,
                "incident_response": None,
                "incident_id": None,
                "no_incident": True,
            }

        incident_get_url = (
            f"{self.BASE_URL}/incident.get"
            f"?custid={api_key}"
            f"&incidentid={incident_id}"
        )
        async with self.session.get(incident_get_url, timeout=request_timeout) as resp:
            if resp.status != 200:
                body_text = await resp.text()
                raise HTTPException(
                    status_code=502,
                    detail=f"PhishLabs incident.get error {resp.status}: {body_text[:1000]}",
                )
            incident_response = await resp.json(content_type=None)

        logger.debug("Phishlabs Incident Response: %s", incident_response)
        return {
            "createincident_response": createincident_response,
            "incident_response": incident_response,
            "incident_id": str(incident_id) if incident_id is not None else None,
            "no_incident": False,
            "action": action,
            "catcode": catcode,
            "flags": flags,
        }


async def call_phishlabs_createincident_flow(
    url: str,
    api_key: str,
    catcode: str = "12345",
    action: PhishLabsAction = "check",
) -> Dict[str, Any]:
    async with PhishLabsAPIClient() as client:
        return await client.call_createincident_flow(url, api_key, catcode, action=action)
