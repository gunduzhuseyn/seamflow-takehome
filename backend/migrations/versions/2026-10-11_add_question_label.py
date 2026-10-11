"""add question_label and generic verdicts

Revision ID: 7c1f3a9e2b54
Revises: bdebdde8431e
Create Date: 2026-10-11 18:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c1f3a9e2b54"
down_revision: str | Sequence[str] | None = "bdebdde8431e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OWNER_WHERE = sa.text("duplicate_of IS NULL AND status IN ('processing', 'completed')")


def _swap_verdicts(column: str, pairs: list[tuple[str, str]]) -> None:
    """Drop the check constraint, map the values, add the new constraint."""
    # op.f: the name is final, so the naming convention leaves it alone.
    op.drop_constraint(
        op.f(f"classifications_{column}_check"), "classifications", type_="check"
    )
    for old, new in pairs:
        op.execute(
            sa.text(
                f"UPDATE classifications SET {column} = :new WHERE {column} = :old"  # noqa: S608
            ).bindparams(new=new, old=old)
        )
    op.create_check_constraint(
        op.f(f"classifications_{column}_check"),
        "classifications",
        sa.column(column).in_([new for _, new in pairs]),
    )


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "classifications",
        sa.Column(
            "question_label", sa.Text(), server_default="hot dog", nullable=False
        ),
    )
    for column in ("verdict", "final_verdict"):
        _swap_verdicts(column, [("hot_dog", "match"), ("not_hot_dog", "no_match")])
    op.drop_index(
        "uq_classifications_hash_owner",
        table_name="classifications",
        postgresql_where=OWNER_WHERE,
    )
    op.create_index(
        "uq_classifications_hash_owner",
        "classifications",
        ["org_id", "image_sha256", "question_label"],
        unique=True,
        postgresql_where=OWNER_WHERE,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "uq_classifications_hash_owner",
        table_name="classifications",
        postgresql_where=OWNER_WHERE,
    )
    op.create_index(
        "uq_classifications_hash_owner",
        "classifications",
        ["org_id", "image_sha256"],
        unique=True,
        postgresql_where=OWNER_WHERE,
    )
    for column in ("verdict", "final_verdict"):
        _swap_verdicts(column, [("match", "hot_dog"), ("no_match", "not_hot_dog")])
    op.drop_column("classifications", "question_label")
