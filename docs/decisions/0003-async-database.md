# Async database

## Decision

SQLAlchemy 2 async with asyncpg. Alembic uses the async environment.
Context: the arq worker, the Anthropic SDK, and the S3 client all run
on asyncio.

## Why, cost, revert

- Why: one driver model. Sync and async session handling never mix.
- Cost: related data must be loaded on purpose in each query.
- Revert: switch the engine, session factory, driver, and Alembic environment to the sync forms.
