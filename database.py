from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# -------------------------
# DATABASE URL
# -------------------------
# Use environment variable for security
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

# -------------------------
# SQLAlchemy Engine
# -------------------------
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # avoids stale connections
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
