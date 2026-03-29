from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from onx.core.config import get_settings


def build_alembic_config() -> Config:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "onx" / "alembic"))
    config.set_main_option("sqlalchemy.url", get_settings().database_url)
    return config


def upgrade_to_head() -> None:
    command.upgrade(build_alembic_config(), "head")
