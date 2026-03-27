from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import shutil, os
from uuid import UUID
from app.database import get_db
from app.models.resume import Resume
from app.models.schemas import ResumeUploadResponse
from app.services.resume_parser import extract_text_from_pdf, parse_resume
from app.config import get_settings

router = APIRouter()
settings = get_settings()

@router.post("/upload", response_model=ResumeUploadResponse)
async def upload_resume(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    # Validate file type
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    # Validate file size
    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > settings.MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Max size is {settings.MAX_FILE_SIZE_MB}MB"
        )

    # Save file to disk
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    file_path = f"{settings.UPLOAD_DIR}/{file.filename}"
    with open(file_path, "wb") as f:
        f.write(contents)

    # Extract and parse
    try:
        raw_text = extract_text_from_pdf(file_path)
        parsed_data = parse_resume(raw_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse resume: {str(e)}")

    # Save to database
    resume = Resume(
        filename=file.filename,
        raw_text=raw_text,
        parsed_data=parsed_data,
        ats_score=parsed_data.get("ats_score")
    )
    db.add(resume)
    await db.commit()
    await db.refresh(resume)

    return resume

@router.get("/{resume_id}", response_model=ResumeUploadResponse)
async def get_resume(
    resume_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Resume).where(Resume.id == resume_id))
    resume = result.scalar_one_or_none()

    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    return resume