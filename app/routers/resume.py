from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import os
from uuid import UUID
from app.database import get_db
from app.models.resume import Resume
from app.models.user import User
from app.models.schemas import ResumeUploadResponse
from app.services.auth_service import get_current_user
from app.services.resume_parser import extract_text_from_pdf, parse_resume
from app.services.mistral_service import elaborate_resume
from app.services.embedding_service import store_resume_embedding, resume_collection
from app.config import get_settings

router = APIRouter()
settings = get_settings()


async def refresh_resume_analysis(resume: Resume, db: AsyncSession) -> Resume:
    parsed_data = parse_resume(resume.raw_text or "")
    if parsed_data != resume.parsed_data or parsed_data.get("ats_score") != resume.ats_score:
        resume.parsed_data = parsed_data
        resume.ats_score = parsed_data.get("ats_score")
        await db.commit()
        await db.refresh(resume)
    return resume

@router.post("/upload", response_model=ResumeUploadResponse)
async def upload_resume(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > settings.MAX_FILE_SIZE_MB:
        raise HTTPException(status_code=400, detail=f"File too large. Max size is {settings.MAX_FILE_SIZE_MB}MB")

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    file_path = f"{settings.UPLOAD_DIR}/{file.filename}"
    with open(file_path, "wb") as f:
        f.write(contents)

    try:
        raw_text = extract_text_from_pdf(file_path)
        parsed_data = parse_resume(raw_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse resume: {str(e)}")

    resume = Resume(
        filename=file.filename,
        raw_text=raw_text,
        parsed_data=parsed_data,
        ats_score=parsed_data.get("ats_score"),
        user_id=current_user.id
    )
    db.add(resume)
    await db.commit()
    await db.refresh(resume)

    store_resume_embedding(
        resume_id=str(resume.id),
        text=raw_text,
        metadata={
            "filename": resume.filename,
            "skills": ",".join(parsed_data.get("skills", [])),
            "ats_score": str(parsed_data.get("ats_score", 0))
        }
    )
    return resume

@router.get("/")
async def list_resumes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Resume).where(Resume.user_id == current_user.id)
    )
    resumes = result.scalars().all()
    for resume in resumes:
        await refresh_resume_analysis(resume, db)
    return resumes

@router.get("/{resume_id}", response_model=ResumeUploadResponse)
async def get_resume(
    resume_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Resume).where(
            Resume.id == resume_id,
            Resume.user_id == current_user.id
        )
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    return await refresh_resume_analysis(resume, db)

@router.get("/{resume_id}/download")
async def download_resume(
    resume_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Resume).where(
            Resume.id == resume_id,
            Resume.user_id == current_user.id
        )
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    
    file_path = f"{settings.UPLOAD_DIR}/{resume.filename}"
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found on server")
        
    return FileResponse(path=file_path, filename=resume.filename, media_type='application/pdf')

@router.post("/{resume_id}/elaborate")
async def elaborate_resume_endpoint(
    resume_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Resume).where(
            Resume.id == resume_id,
            Resume.user_id == current_user.id
        )
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
        
    elaboration = elaborate_resume(resume.raw_text or "")
    return {"elaboration": elaboration}
