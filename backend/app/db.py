from collections.abc import Generator
from pathlib import Path
from sqlite3 import Connection
from sqlalchemy import event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import ConnectionPoolEntry
from sqlmodel import Session, SQLModel, create_engine
from . import models  # Register every table before create_all.
from .config import get_settings


def build_engine(database_url: str) -> Engine:
    url = make_url(database_url)
    if url.drivername == "sqlite" and url.database not in (None, ":memory:"):
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(database_url, connect_args={"check_same_thread": False} if url.drivername == "sqlite" else {})
    if url.drivername == "sqlite":
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection: Connection, _: ConnectionPoolEntry) -> None:
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine


def init_db(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        if session.get(models.Settings, 1) is None:
            session.add(models.Settings())
            session.commit()


def get_session() -> Generator[Session, None, None]:
    from .main import app
    with Session(app.state.engine) as session:
        yield session
