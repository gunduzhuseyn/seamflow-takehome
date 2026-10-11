"""Idempotent seed: the demo org and the seed user as its admin.

Run with `uv run python -m app.seed`. It runs after `alembic upgrade head`
locally and in the Railway pre-deploy command.
"""

import asyncio
import logging

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Membership, Organization, Role, User
from app.core.clerk import ClerkBackend, ClerkClient
from app.core.config import PLACEHOLDERS, Settings
from app.core.db import create_engine, create_sessionmaker
from app.core.logging import configure_logging

log = logging.getLogger("app.seed")

DEMO_ORG_NAME = "Demo"
DEMO_ORG_SLUG = "demo"


class SeedConfigError(ValueError):
    """A seed setting still has its .env.example value."""


async def seed(session: AsyncSession, clerk: ClerkClient, settings: Settings) -> None:
    # In every environment: a placeholder login is public, so Clerk never
    # gets an account with it.
    for name in ("SEED_USER_EMAIL", "SEED_USER_PASSWORD"):
        if getattr(settings, name) == PLACEHOLDERS[name]:
            raise SeedConfigError(
                f"{name} still has its .env.example value. Set it in .env."
            )
    org = await session.scalar(
        select(Organization).where(Organization.slug == DEMO_ORG_SLUG)
    )
    if org is None:
        org = Organization(name=DEMO_ORG_NAME, slug=DEMO_ORG_SLUG)
        session.add(org)
        await session.flush()

    email = settings.SEED_USER_EMAIL
    # Clerk keeps the password of an existing user. Only a new user gets it.
    clerk_user_id = await clerk.get_or_create_user(email, settings.SEED_USER_PASSWORD)
    user = await session.scalar(
        select(User).where(
            or_(User.clerk_user_id == clerk_user_id, User.email == email)
        )
    )
    if user is None:
        user = User(clerk_user_id=clerk_user_id, email=email)
        session.add(user)
        await session.flush()
    else:
        user.clerk_user_id = clerk_user_id
        user.email = email

    membership = await session.get(Membership, (user.id, org.id))
    if membership is None:
        session.add(Membership(user_id=user.id, org_id=org.id, role=Role.admin))
    else:
        membership.role = Role.admin

    await session.commit()


async def main() -> None:
    settings = Settings()  # pyright: ignore[reportCallIssue]
    configure_logging(settings)
    engine = create_engine(settings)
    try:
        async with create_sessionmaker(engine)() as session:
            await seed(session, ClerkBackend(settings.CLERK_SECRET_KEY), settings)
    finally:
        await engine.dispose()
    log.info("Seeded org '%s' and user %s", DEMO_ORG_SLUG, settings.SEED_USER_EMAIL)


if __name__ == "__main__":
    asyncio.run(main())
