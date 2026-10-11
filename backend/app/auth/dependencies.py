import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Any

import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Membership, Organization, Role, User
from app.core.clerk import ClerkClient, ClerkUserNotFoundError, get_clerk
from app.core.config import Settings
from app.core.db import SessionDep

# Clerk's Python SDK uses the same clock skew allowance.
LEEWAY_SECONDS = 5
# Higher rank includes the rights of every lower rank.
ROLE_RANK = {Role.member: 0, Role.admin: 1}

bearer = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def verify_session_token(token: str, settings: Settings) -> dict[str, Any]:
    """Check a Clerk session token offline with the instance public key."""
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            settings.CLERK_JWT_KEY,
            algorithms=["RS256"],
            leeway=LEEWAY_SECONDS,
            options={"require": ["exp", "nbf", "sub", "sid", "iss", "azp"]},
        )
    except jwt.PyJWTError as error:
        raise _unauthorized("Invalid session token") from error
    if claims["azp"] not in settings.CLERK_AUTHORIZED_PARTIES:
        raise _unauthorized("Invalid session token")
    return claims


def _slug(text: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "org"
    return f"{base[:40]}-{uuid.uuid4().hex[:8]}"


async def _create_user(
    session: AsyncSession, clerk: ClerkClient, clerk_user_id: str
) -> User:
    """Create the user, a personal org, and an admin membership in one commit."""
    try:
        email = await clerk.get_user(clerk_user_id)
    except ClerkUserNotFoundError as error:
        raise _unauthorized("Unknown user") from error
    local_part = email.split("@", 1)[0]
    user = User(clerk_user_id=clerk_user_id, email=email)
    org = Organization(name=local_part, slug=_slug(local_part))
    try:
        # flush sends the inserts, so a duplicate fails here, not at commit.
        session.add_all([user, org])
        await session.flush()
        session.add(Membership(user_id=user.id, org_id=org.id, role=Role.admin))
        await session.commit()
    except IntegrityError:
        # A parallel first request created the user. Use that row.
        await session.rollback()
        existing = await session.scalar(
            select(User).where(User.clerk_user_id == clerk_user_id)
        )
        if existing is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="Another account already uses this email",
            ) from None
        return existing
    return user


async def get_current_user(
    request: Request,
    session: SessionDep,
    clerk: Annotated[ClerkClient, Depends(get_clerk)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    if credentials is None:
        raise _unauthorized("Not authenticated")
    settings: Settings = request.app.state.settings
    claims = verify_session_token(credentials.credentials, settings)
    clerk_user_id: str = claims["sub"]
    user = await session.scalar(select(User).where(User.clerk_user_id == clerk_user_id))
    if user is None:
        user = await _create_user(session, clerk, clerk_user_id)
    # The access log reads it.
    request.state.user_id = str(user.id)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


@dataclass
class ActiveOrg:
    user: User
    org: Organization
    role: Role


async def get_active_org(
    request: Request,
    session: SessionDep,
    user: CurrentUser,
    x_org_id: Annotated[uuid.UUID | None, Header()] = None,
) -> ActiveOrg:
    """The org from the X-Org-Id header, else the user's first membership."""
    query = (
        select(Membership, Organization)
        .join(Organization, Organization.id == Membership.org_id)
        .where(Membership.user_id == user.id)
    )
    if x_org_id is not None:
        query = query.where(Membership.org_id == x_org_id)
    query = query.order_by(Membership.created_at, Membership.org_id).limit(1)
    row = (await session.execute(query)).first()
    if row is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not a member")
    membership, org = row
    # The access log reads it.
    request.state.org_id = str(org.id)
    return ActiveOrg(user=user, org=org, role=membership.role)


OrgContext = Annotated[ActiveOrg, Depends(get_active_org)]


def require_role(role: Role | str) -> Callable[[ActiveOrg], Awaitable[ActiveOrg]]:
    """Dependency that allows the given role or a higher one in the active org."""
    needed = ROLE_RANK[Role(role)]

    async def check(context: OrgContext) -> ActiveOrg:
        if ROLE_RANK[context.role] < needed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Role not allowed")
        return context

    return check
