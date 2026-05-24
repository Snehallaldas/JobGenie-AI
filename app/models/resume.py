from sqlalchemy import Column, String, Float, DateTime, JSON, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid
from app.database import Base

class Resume(Base):
    __tablename__ = "resumes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    filename = Column(String(255), nullable=False)
    raw_text = Column(Text, nullable=False)
    parsed_data = Column(JSON, nullable=True)
    ats_score = Column(Float, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
