"""initial

Revision ID: 0151a2d2d208
Revises:
Create Date: 2026-10-11 07:42:19.018253

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0151a2d2d208"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
