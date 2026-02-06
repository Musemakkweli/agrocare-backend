# database.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# -------------------------
# DATABASE URL
# -------------------------
# It's better to use environment variables for security
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres.jwdhnfdgkokpyvrgmtxd:c01rJFqtYpcy8JU7@aws-1-eu-west-3.pooler.supabase.com:6543/postgres"
)

# -------------------------
# SQLAlchemy Engine
# -------------------------
engine = create_engine(
    DATABASE_URL,
    connect_args={"sslmode": "require"}  # Required for Supabase/PostgreSQL SSL
)

# -------------------------
# Session Local
# -------------------------
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# -------------------------
# Base Class for Models
# -------------------------
Base = declarative_base()

# -------------------------
# Dependency for FastAPI
# -------------------------
def get_db():
    """
    Provide a database session for FastAPI endpoints.
    Closes session automatically after request.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
