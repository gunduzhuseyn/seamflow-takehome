"""Org isolation for every table with an org_id column, from table metadata."""

import uuid
from dataclasses import dataclass
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import app.main  # noqa: F401  # pyright: ignore[reportUnusedImport]  # loads every model
from app.core.db import Base
from tests.fakes import TokenFactory
from tests.tenancy_registry import EXEMPT, REGISTRY, ItemAction, Report, TenantRoutes

ORG_TABLES = sorted(t.name for t in Base.metadata.tables.values() if "org_id" in t.c)
# A registry entry without a table also runs, so it fails instead of hiding.
CHECKED = sorted((set(ORG_TABLES) | set(REGISTRY)) - set(EXEMPT))


def _with(method: str) -> list[str]:
    """Tables whose routes include the method. An unregistered table runs too."""
    return [t for t in CHECKED if t not in REGISTRY or method in REGISTRY[t].methods]


FOREIGN_CASES = [(t, m) for m in ("get", "patch", "delete") for t in _with(m)]
ACTION_CASES = [(t, a) for t in CHECKED if t in REGISTRY for a in REGISTRY[t].actions]
REPORT_CASES = [(t, r) for t in CHECKED if t in REGISTRY for r in REGISTRY[t].reports]


@dataclass
class Tenant:
    org_id: uuid.UUID
    user_id: uuid.UUID
    headers: dict[str, str]
    rows: list[uuid.UUID]


async def _tenant(session: AsyncSession, make_token: TokenFactory, name: str) -> Tenant:
    org_id, user_id = uuid.uuid4(), uuid.uuid4()
    await session.execute(
        text("INSERT INTO organizations (id, name, slug) VALUES (:id, :n, :n)"),
        {"id": org_id, "n": f"org-{name}"},
    )
    await session.execute(
        text("INSERT INTO users (id, clerk_user_id, email) VALUES (:id, :c, :e)"),
        {"id": user_id, "c": f"user_{name}", "e": f"{name}@example.com"},
    )
    await session.execute(
        text(
            "INSERT INTO memberships (user_id, org_id, role) VALUES (:u, :o, 'admin')"
        ),
        {"u": user_id, "o": org_id},
    )
    token = make_token(f"user_{name}")
    return Tenant(org_id, user_id, {"Authorization": f"Bearer {token}"}, [])


async def _two_tenants(
    session: AsyncSession, make_token: TokenFactory, routes: TenantRoutes
) -> tuple[Tenant, Tenant]:
    a = await _tenant(session, make_token, "a")
    b = await _tenant(session, make_token, "b")
    for tenant in (a, b):
        for _ in range(2):
            tenant.rows.append(
                await routes.insert_row(session, tenant.org_id, tenant.user_id)
            )
    await session.commit()
    return a, b


async def _snapshot(
    session: AsyncSession, table: str, row_id: uuid.UUID
) -> dict[str, Any]:
    result = await session.execute(
        text(f"SELECT * FROM {table} WHERE id = :id"),  # noqa: S608
        {"id": row_id},
    )
    return dict(result.mappings().one())


def _routes(table: str) -> TenantRoutes:
    assert table in ORG_TABLES, f"{table} is registered but has no org_id table"
    assert table in REGISTRY, f"{table} has org_id but no tenancy registry entry"
    return REGISTRY[table]


@pytest.mark.parametrize("table", ORG_TABLES)
def test_every_org_table_is_registered_or_exempt(table: str) -> None:
    assert (table in REGISTRY) != (table in EXEMPT)


def test_exemptions_are_explicit() -> None:
    assert sorted(EXEMPT) == ["memberships"]
    assert all(reason.strip() for reason in EXEMPT.values())
    assert set(EXEMPT) <= set(ORG_TABLES)


async def test_metadata_lists_every_org_table_in_the_database(
    db_session: AsyncSession,
) -> None:
    result = await db_session.execute(
        text(
            "SELECT table_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND column_name = 'org_id'"
        )
    )
    assert sorted(result.scalars().all()) == ORG_TABLES


@pytest.mark.parametrize("table", _with("list"))
async def test_list_shows_only_own_rows(
    table: str, client: AsyncClient, db_session: AsyncSession, make_token: TokenFactory
) -> None:
    routes = _routes(table)
    a, _ = await _two_tenants(db_session, make_token, routes)

    response = await client.get(routes.collection, headers=a.headers)

    assert response.status_code == 200
    body = response.json()
    # A paged list wraps its rows in `items`.
    rows: list[dict[str, Any]] = body["items"] if "items" in body else body
    assert sorted(row["id"] for row in rows) == sorted(map(str, a.rows))


@pytest.mark.parametrize("table", _with("get"))
async def test_get_own_row(
    table: str, client: AsyncClient, db_session: AsyncSession, make_token: TokenFactory
) -> None:
    routes = _routes(table)
    a, _ = await _two_tenants(db_session, make_token, routes)

    response = await client.get(routes.item(a.rows[0]), headers=a.headers)

    assert response.status_code == 200
    assert response.json()["id"] == str(a.rows[0])


@pytest.mark.parametrize(("table", "method"), FOREIGN_CASES)
async def test_foreign_row_is_404_and_unchanged(
    table: str,
    method: str,
    client: AsyncClient,
    db_session: AsyncSession,
    make_token: TokenFactory,
) -> None:
    routes = _routes(table)
    a, b = await _two_tenants(db_session, make_token, routes)
    target = b.rows[0]
    before = await _snapshot(db_session, table, target)

    if method == "patch":
        response = await client.patch(
            routes.item(target), headers=a.headers, json=routes.update_body
        )
    else:
        response = await client.request(method, routes.item(target), headers=a.headers)

    assert response.status_code == 404
    db_session.expire_all()
    assert await _snapshot(db_session, table, target) == before


@pytest.mark.parametrize(
    ("table", "action"), ACTION_CASES, ids=[f"{t}-{a.suffix}" for t, a in ACTION_CASES]
)
async def test_foreign_row_action_is_404_and_unchanged(
    table: str,
    action: ItemAction,
    client: AsyncClient,
    db_session: AsyncSession,
    make_token: TokenFactory,
) -> None:
    routes = _routes(table)
    a, b = await _two_tenants(db_session, make_token, routes)
    target = b.rows[0]
    before = await _snapshot(db_session, table, target)

    response = await client.post(
        f"{routes.item(target)}/{action.suffix}", headers=a.headers, json=action.body
    )

    assert response.status_code == 404
    db_session.expire_all()
    assert await _snapshot(db_session, table, target) == before


@pytest.mark.parametrize(
    ("table", "report"), REPORT_CASES, ids=[f"{t}-{r.path}" for t, r in REPORT_CASES]
)
async def test_report_covers_only_own_rows(
    table: str,
    report: Report,
    client: AsyncClient,
    db_session: AsyncSession,
    make_token: TokenFactory,
) -> None:
    routes = _routes(table)
    a, _ = await _two_tenants(db_session, make_token, routes)

    response = await client.get(report.path, headers=a.headers)

    assert response.status_code == 200
    assert report.count(response) == len(a.rows)


@pytest.mark.parametrize("table", _with("create"))
async def test_create_lands_in_active_org(
    table: str, client: AsyncClient, db_session: AsyncSession, make_token: TokenFactory
) -> None:
    routes = _routes(table)
    a, _ = await _two_tenants(db_session, make_token, routes)

    response = await client.post(
        routes.collection, headers=a.headers, json=routes.create_body
    )

    assert response.status_code == 201
    stored = await _snapshot(db_session, table, uuid.UUID(response.json()["id"]))
    assert stored["org_id"] == a.org_id
