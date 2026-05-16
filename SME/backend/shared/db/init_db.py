from backend.shared.db.database import Base, engine
from backend.shared.models import entities  # noqa: F401


def init_db() -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS onboarding")
        conn.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS kyc")
        conn.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS loan")
        conn.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS repayment")
        conn.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS transaction")
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
