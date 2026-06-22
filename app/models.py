import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Enum, JSON, Boolean
from app.database import Base, engine

# Define payment methods and status options
class PaymentProvider(str, enum.Enum):
    ECOCASH = "ECOCASH"
    INNBUCKS = "INNBUCKS"
    PAYNOW = "PAYNOW"

class TransactionStatus(str, enum.Enum):
    PENDING = "PENDING"
    SUCCESSFUL = "SUCCESSFUL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

# Table 1: Tracks where the user is in the WhatsApp chat
class UserSession(Base):
    __tablename__ = "user_sessions"

    whatsapp_num = Column(String, primary_key=True, index=True)
    current_state = Column(String, default="MAIN_MENU")
    context_data = Column(JSON, default={}) # Stores meter number or amount temporarily
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Table 2: Logs every payment attempt
class TransactionRecord(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    reference_number = Column(String, unique=True, index=True, nullable=False) # e.g., SAM-20241126-A1B2
    whatsapp_num = Column(String, nullable=False)
    meter_number = Column(String, nullable=False)
    amount_usd = Column(Numeric(10, 2), nullable=False)
    provider = Column(Enum(PaymentProvider), nullable=False)
    status = Column(Enum(TransactionStatus), default=TransactionStatus.PENDING)
    provider_ref = Column(String, nullable=True) # ID returned by EcoCash/Paynow
    created_at = Column(DateTime, default=datetime.utcnow)
    token = Column(String(50), nullable=True)
    is_token_used = Column(Boolean, default=False)

# Automatically create the tables in PostgreSQL
if __name__ == "__main__":
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully!")