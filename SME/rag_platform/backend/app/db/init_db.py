import time

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db.database import Base, engine
from app.models import entities  # noqa: F401


def init_db() -> None:
    attempts = 30
    for attempt in range(1, attempts + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text('SELECT 1'))
            break
        except OperationalError:
            if attempt == attempts:
                raise
            time.sleep(2)
    Base.metadata.create_all(bind=engine)


if __name__ == '__main__':
    init_db()
