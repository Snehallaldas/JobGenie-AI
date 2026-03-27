from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional

class ResumeUploadResponse(BaseModel):
    id: UUID
    filename: str
    raw_text: str
    parsed_data: Optional[dict] = None
    ats_score: Optional[float] = None
    uploaded_at: datetime

    class Config:
        from_attributes = True