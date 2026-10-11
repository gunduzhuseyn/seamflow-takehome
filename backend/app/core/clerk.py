from typing import Protocol

from clerk_backend_api import Clerk
from clerk_backend_api.models import ClerkErrors
from fastapi import Request


class ClerkUserNotFoundError(LookupError):
    """Clerk has no user with this id, or the user has no email address."""


class ClerkClient(Protocol):
    """The Clerk operations this app uses. Tests and the seed test use a fake."""

    async def get_user(self, clerk_user_id: str) -> str:
        """Return the primary email address of the Clerk user."""
        ...

    async def get_or_create_user(self, email: str, password: str) -> str:
        """Return the Clerk user id for this email. Create the user if missing."""
        ...


def get_clerk(request: Request) -> ClerkClient:
    return request.app.state.clerk


class ClerkBackend:
    """ClerkClient on the Clerk Backend API SDK."""

    def __init__(self, secret_key: str) -> None:
        self._sdk = Clerk(bearer_auth=secret_key)

    async def get_user(self, clerk_user_id: str) -> str:
        try:
            user = await self._sdk.users.get_async(user_id=clerk_user_id)
        except ClerkErrors as error:
            if error.status_code == 404:
                raise ClerkUserNotFoundError(clerk_user_id) from error
            raise
        for address in user.email_addresses:
            if address.id == user.primary_email_address_id:
                return address.email_address
        raise ClerkUserNotFoundError(clerk_user_id)

    async def get_or_create_user(self, email: str, password: str) -> str:
        found = await self._sdk.users.list_async(request={"email_address": [email]})
        if found:
            return found[0].id
        created = await self._sdk.users.create_async(
            email_address=[email], password=password
        )
        return created.id
