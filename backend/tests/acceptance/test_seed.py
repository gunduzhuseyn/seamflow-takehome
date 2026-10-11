import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import PLACEHOLDERS, Settings
from app.seed import SeedConfigError, seed
from tests.fakes import FakeClerk


async def test_seed_twice_leaves_one_demo_org_user_and_membership(
    db_session: AsyncSession, settings: Settings, fake_clerk: FakeClerk
) -> None:
    await seed(db_session, fake_clerk, settings)
    await seed(db_session, fake_clerk, settings)

    orgs = (await db_session.execute(text("SELECT id, slug FROM organizations"))).all()
    users = (
        await db_session.execute(text("SELECT id, clerk_user_id, email FROM users"))
    ).all()
    memberships = (
        await db_session.execute(text("SELECT user_id, org_id, role FROM memberships"))
    ).all()

    assert [slug for _, slug in orgs] == ["demo"]
    assert len(users) == 1
    user_id, clerk_user_id, email = users[0]
    assert email == settings.SEED_USER_EMAIL
    assert fake_clerk.emails[clerk_user_id] == settings.SEED_USER_EMAIL
    assert memberships == [(user_id, orgs[0][0], "admin")]
    assert fake_clerk.created == [settings.SEED_USER_EMAIL]


@pytest.mark.parametrize("name", ["SEED_USER_EMAIL", "SEED_USER_PASSWORD"])
async def test_seed_refuses_placeholder_login_before_clerk(
    db_session: AsyncSession, settings: Settings, fake_clerk: FakeClerk, name: str
) -> None:
    placeholder_settings = settings.model_copy(update={name: PLACEHOLDERS[name]})

    with pytest.raises(SeedConfigError, match=name):
        await seed(db_session, fake_clerk, placeholder_settings)

    assert fake_clerk.created == []
    rows = await db_session.execute(
        text(
            "SELECT (SELECT count(*) FROM users), (SELECT count(*) FROM organizations),"
            " (SELECT count(*) FROM memberships)"
        )
    )
    assert rows.one() == (0, 0, 0)
