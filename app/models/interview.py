from sqlalchemy import Column, String, Float, DateTime, JSON, Integer, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid
from app.database import Base

class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resume_id = Column(UUID(as_uuid=True), ForeignKey("resumes.id"), nullable=False)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
    questions = Column(JSON, nullable=True)      # generated questions
    answers = Column(JSON, nullable=True)         # submitted answers + scores
    average_score = Column(Float, nullable=True)
    report = Column(JSON, nullable=True)          # final feedback report
    status = Column(String(50), default="started")  # started|in_progress|completed
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)