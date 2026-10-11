from alembic.config import Config
from alembic.script import ScriptDirectory


def test_single_alembic_head(alembic_config: Config) -> None:
    heads = ScriptDirectory.from_config(alembic_config).get_heads()

    assert len(heads) == 1
