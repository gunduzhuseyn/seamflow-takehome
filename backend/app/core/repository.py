import uuid
from collections.abc import Sequence

from sqlalchemy import ForeignKey, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class OrgScoped(Base):
    """Base of every tenant-scoped table: a uuid id and an org_id column."""

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )


class Repository[M: OrgScoped]:
    """Data access for one tenant-scoped model.

    Every method takes org_id and filters by it. A row of another org is
    not found. Methods flush; the caller commits.
    """

    model: type[M]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, org_id: uuid.UUID, id: uuid.UUID) -> M | None:
        return await self.session.scalar(
            select(self.model).where(self.model.org_id == org_id, self.model.id == id)
        )

    async def list(self, org_id: uuid.UUID) -> Sequence[M]:
        result = await self.session.scalars(
            select(self.model).where(self.model.org_id == org_id)
        )
        return result.all()

    async def create(self, org_id: uuid.UUID, **values: object) -> M:
        row = self.model(org_id=org_id, **values)
        self.session.add(row)
        await self.session.flush()
        return row

    async def update(
        self, org_id: uuid.UUID, id: uuid.UUID, **values: object
    ) -> M | None:
        row = await self.get(org_id, id)
        if row is None:
            return None
        for name, value in values.items():
            setattr(row, name, value)
        await self.session.flush()
        return row

    async def delete(self, org_id: uuid.UUID, id: uuid.UUID) -> bool:
        row = await self.get(org_id, id)
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True
