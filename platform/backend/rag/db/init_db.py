import logging
import time

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from rag.db.database import Base, engine
from rag.models import entities  # noqa: F401

logger = logging.getLogger(__name__)


def init_db() -> None:
    for attempt in range(1, 31):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            break
        except OperationalError:
            if attempt == 30:
                raise
            time.sleep(2)

    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    Base.metadata.create_all(bind=engine)
    logger.info("RAG database initialised.")
