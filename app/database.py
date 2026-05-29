from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

# Create the standard synchronous engine using psycopg2
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,  # Automatically checks and repairs broken connections
    pool_size=10,        # Keeps up to 10 active database connections open
    max_overflow=20      # Allows up to 20 extra connections during spikes
)

# Create a session factory for database operations
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Declarative base class for our models to inherit from
Base = declarative_base()

def get_db():
    """
    FastAPI Dependency that yields a database session 
    and guarantees it closes after the request completes.
    """
    db = SessionLocal()
    try:
         yield db
    finally:
         db.close()