import uuid
from datetime import timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import AsyncClient, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fakes import FakeClerk, TokenFactory


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def count_rows(session: AsyncSession, table: str) -> int:
    result = await session.execute(text(f"SELECT count(*) FROM {table}"))  # noqa: S608
    return result.scalar_one()


async def all_counts(session: AsyncSession) -> tuple[int, int, int]:
    return (
        await count_rows(session, "users"),
        await count_rows(session, "organizations"),
        await count_rows(session, "memberships"),
    )


async def insert_user(session: AsyncSession, clerk_user_id: str, email: str) -> str:
    user_id = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO users (id, clerk_user_id, email) "
            "VALUES (:id, :clerk_user_id, :email)"
        ),
        {"id": user_id, "clerk_user_id": clerk_user_id, "email": email},
    )
    return user_id


async def insert_org(session: AsyncSession, name: str, slug: str) -> str:
    org_id = str(uuid.uuid4())
    await session.execute(
        text("INSERT INTO organizations (id, name, slug) VALUES (:id, :name, :slug)"),
        {"id": org_id, "name": name, "slug": slug},
    )
    return org_id


async def insert_membership(
    session: AsyncSession, user_id: str, org_id: str, role: str
) -> None:
    await session.execute(
        text(
            "INSERT INTO memberships (user_id, org_id, role) "
            "VALUES (:user_id, :org_id, :role)"
        ),
        {"user_id": user_id, "org_id": org_id, "role": role},
    )


async def org_name(session: AsyncSession, org_id: str) -> str:
    result = await session.execute(
        text("SELECT name FROM organizations WHERE id = :id"), {"id": org_id}
    )
    return result.scalar_one()


# 401 cases. A rejected token creates no rows.


async def test_me_without_token_is_401(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    response = await client.get("/me")

    assert response.status_code == 401
    assert await all_counts(db_session) == (0, 0, 0)


async def test_me_with_bad_signature_is_401(
    client: AsyncClient,
    db_session: AsyncSession,
    make_token: TokenFactory,
    fake_clerk: FakeClerk,
) -> None:
    fake_clerk.emails["user_bad"] = "bad@example.com"
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    response = await client.get(
        "/me", headers=bearer(make_token("user_bad", key=other_key))
    )

    assert response.status_code == 401
    assert await all_counts(db_session) == (0, 0, 0)


async def test_me_with_expired_token_is_401(
    client: AsyncClient,
    db_session: AsyncSession,
    make_token: TokenFactory,
    fake_clerk: FakeClerk,
) -> None:
    fake_clerk.emails["user_old"] = "old@example.com"
    token = make_token("user_old", expires_in=timedelta(minutes=-1))

    response = await client.get("/me", headers=bearer(token))

    assert response.status_code == 401
    assert await all_counts(db_session) == (0, 0, 0)


async def test_me_with_wrong_authorized_party_is_401(
    client: AsyncClient,
    db_session: AsyncSession,
    make_token: TokenFactory,
    fake_clerk: FakeClerk,
) -> None:
    fake_clerk.emails["user_azp"] = "azp@example.com"
    token = make_token("user_azp", azp="https://evil.example")

    response = await client.get("/me", headers=bearer(token))

    assert response.status_code == 401
    assert await all_counts(db_session) == (0, 0, 0)


# First login.


async def test_first_login_creates_user_and_personal_org_once(
    client: AsyncClient,
    db_session: AsyncSession,
    make_token: TokenFactory,
    fake_clerk: FakeClerk,
) -> None:
    fake_clerk.emails["user_new"] = "ada.lovelace@example.com"
    headers = bearer(make_token("user_new"))

    response = await client.get("/me", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "ada.lovelace@example.com"
    assert body["role"] == "admin"
    assert body["org"]["name"] == "ada.lovelace"
    assert len(body["memberships"]) == 1

    rows = (
        await db_session.execute(
            text(
                "SELECT u.email, o.id, o.name, m.role FROM users u "
                "JOIN memberships m ON m.user_id = u.id "
                "JOIN organizations o ON o.id = m.org_id "
                "WHERE u.clerk_user_id = 'user_new'"
            )
        )
    ).all()
    assert len(rows) == 1
    email, stored_org_id, stored_org_name, role = rows[0]
    assert email == "ada.lovelace@example.com"
    assert str(stored_org_id) == body["org"]["id"]
    assert stored_org_name == "ada.lovelace"
    assert role == "admin"
    assert await all_counts(db_session) == (1, 1, 1)

    second = await client.get("/me", headers=headers)

    assert second.status_code == 200
    assert second.json()["org"]["id"] == body["org"]["id"]
    assert await all_counts(db_session) == (1, 1, 1)


async def test_parallel_first_logins_resolve_to_one_user(
    client: AsyncClient,
    db_session: AsyncSession,
    make_token: TokenFactory,
    fake_clerk: FakeClerk,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second first login for the same sub finishes while this one waits."""
    fake_clerk.emails["user_race"] = "race@example.com"
    headers = bearer(make_token("user_race"))
    real_get_user = fake_clerk.get_user
    other: list[Response] = []

    async def get_user_while_other_request_wins(clerk_user_id: str) -> str:
        if not other:
            other.append(Response(0))
            other[0] = await client.get("/me", headers=headers)
        return await real_get_user(clerk_user_id)

    monkeypatch.setattr(fake_clerk, "get_user", get_user_while_other_request_wins)

    response = await client.get("/me", headers=headers)

    assert other[0].status_code == 200
    assert response.status_code == 200
    assert response.json()["user"]["id"] == other[0].json()["user"]["id"]
    assert response.json()["org"]["id"] == other[0].json()["org"]["id"]
    assert await all_counts(db_session) == (1, 1, 1)


# Active org.


async def test_org_header_for_foreign_org_is_403(
    client: AsyncClient,
    db_session: AsyncSession,
    make_token: TokenFactory,
) -> None:
    user_id = await insert_user(db_session, "user_a", "a@example.com")
    own_org = await insert_org(db_session, "Own", "own")
    await insert_membership(db_session, user_id, own_org, "admin")
    foreign_org = await insert_org(db_session, "Foreign", "foreign")
    await db_session.commit()

    response = await client.get(
        "/me",
        headers={**bearer(make_token("user_a")), "X-Org-Id": foreign_org},
    )

    assert response.status_code == 403
    assert await all_counts(db_session) == (1, 2, 1)
    assert await org_name(db_session, foreign_org) == "Foreign"


# Roles.


async def test_member_gets_member_role_and_cannot_rename_org(
    client: AsyncClient,
    db_session: AsyncSession,
    make_token: TokenFactory,
) -> None:
    org_id = await insert_org(db_session, "Shared", "shared")
    admin_id = await insert_user(db_session, "user_admin", "admin@example.com")
    member_id = await insert_user(db_session, "user_member", "member@example.com")
    await insert_membership(db_session, admin_id, org_id, "admin")
    await insert_membership(db_session, member_id, org_id, "member")
    await db_session.commit()
    member_headers = bearer(make_token("user_member"))

    me = await client.get("/me", headers=member_headers)

    assert me.status_code == 200
    assert me.json()["org"]["id"] == org_id
    assert me.json()["role"] == "member"

    denied = await client.patch(
        "/orgs/current", headers=member_headers, json={"name": "Taken over"}
    )

    assert denied.status_code == 403
    assert await org_name(db_session, org_id) == "Shared"
    assert await all_counts(db_session) == (2, 1, 2)

    renamed = await client.patch(
        "/orgs/current",
        headers=bearer(make_token("user_admin")),
        json={"name": "Renamed"},
    )

    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Renamed"
    assert await org_name(db_session, org_id) == "Renamed"
    assert await all_counts(db_session) == (2, 1, 2)
