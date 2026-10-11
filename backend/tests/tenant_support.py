"""Helpers for the acceptance tests: an org, a member, and its auth header."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fakes import TokenFactory


async def insert_member(
    session: AsyncSession, org_id: uuid.UUID, name: str, role: str
) -> uuid.UUID:
    user_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO users (id, clerk_user_id, email) VALUES (:id, :c, :e)"),
        {"id": user_id, "c": f"user_{name}", "e": f"{name}@example.com"},
    )
    await session.execute(
        text("INSERT INTO memberships (user_id, org_id, role) VALUES (:u, :o, :r)"),
        {"u": user_id, "o": org_id, "r": role},
    )
    return user_id


async def insert_org(session: AsyncSession, slug: str = "n") -> uuid.UUID:
    org_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO organizations (id, name, slug) VALUES (:id, 'N', :slug)"),
        {"id": org_id, "slug": slug},
    )
    return org_id


def auth_headers(make_token: TokenFactory, name: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(f'user_{name}')}"}


Tenant = tuple[uuid.UUID, uuid.UUID, dict[str, str]]


@pytest.fixture
async def tenant(db_session: AsyncSession, make_token: TokenFactory) -> Tenant:
    org = await insert_org(db_session)
    user = await insert_member(db_session, org, "writer", "member")
    await db_session.commit()
    return org, user, auth_headers(make_token, "writer")
