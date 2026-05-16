from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://sonar:DCjHsU0Rscm9gs08wAo1a390sqIN@bugdaddy-sonarqube-postgres.ctkcsksi0yjl.ap-south-1.rds.amazonaws.com:5432/app?sslmode=require")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
