"""SQLite database engine and session management."""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from swedish_ai_tutor.db.tables import Base


def create_db_engine(db_path: Path) -> Engine:
    """Create a SQLAlchemy engine for the SQLite database.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Configured SQLAlchemy engine.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    return engine


def init_db(engine: Engine) -> None:
    """Create all tables if they don't exist.

    Args:
        engine: SQLAlchemy engine to create tables on.
    """
    Base.metadata.create_all(engine)


def get_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory bound to the engine.

    Args:
        engine: SQLAlchemy engine.

    Returns:
        Session factory callable.
    """
    return sessionmaker(bind=engine)
