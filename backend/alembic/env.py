import os
import sys
from logging.config import fileConfig

# Explicitly add project root to sys.path
# Assuming current file is backend/alembic/env.py
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Load .env automatically for Alembic migrations - MOVED TO TOP
try:
    from dotenv import load_dotenv
    # Try loading from project root and backend folder
    # Assuming this env.py is in backend/alembic, project root is two levels up.
    # And backend folder is one level up.
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    backend_folder = os.path.dirname(os.path.dirname(__file__))

    load_dotenv(os.path.join(project_root, '.env'))
    load_dotenv(os.path.join(project_root, '.env.dev'))
    load_dotenv(os.path.join(backend_folder, '.env'))
    load_dotenv(os.path.join(backend_folder, '.env.dev'))
except ImportError:
    pass

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Import Base for metadata
from backend.core.database import Base

# Import all models to ensure they are registered with Base.metadata
# It's important to import all models so Alembic can detect schema changes.
from backend.models import *
from backend.core.config import settings

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Overwrite the sqlalchemy.url in the config object with the one from settings.
# This ensures that Alembic uses the database URL defined in environment variables (e.g., production DB).
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
