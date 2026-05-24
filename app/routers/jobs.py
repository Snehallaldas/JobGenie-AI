from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from uuid import UUID
from typing import Optional
from datetime import datetime
import traceback
from app.database import get_db
from app.models.job import Job
from app.models.resume import Resume
from app.models.user import User
from app.services.auth_service import get_current_user
from app.services.embedding_service import (
    store_job_embedding,
    match_resume_to_job,
    compute_skill_gap,
    store_resume_embedding,
    resume_collection,
    job_collection
)

router = APIRouter()

class JobCreate(BaseModel):
    title: str
    company: Optional[str] = None
    description: str
    required_skills: list[str] = []

class JobResponse(BaseModel):
    id: UUID
    title: str
    company: Optional[str]
    description: str
    required_skills: list
    expires_at: datetime

    class Config:
        from_attributes = True

@router.post("/", response_model=JobResponse)
async def create_job(
    job_data: JobCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    job = Job(
        title=job_data.title,
        company=job_data.company,
        description=job_data.description,
        required_skills=job_data.required_skills,
        user_id=current_user.id
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    job_text = f"{job_data.title} {job_data.description}"
    store_job_embedding(
        job_id=str(job.id),
        text=job_text,
        metadata={
            "title": job_data.title,
            "company": job_data.company or "",
            "skills": ",".join(job_data.required_skills)
        }
    )
    return job

@router.get("/")
async def list_jobs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Job).where(Job.expires_at > datetime.utcnow()))
    return result.scalars().all()

@router.get("/match/{resume_id}")
async def match_jobs(
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

    existing = resume_collection.get(ids=[str(resume_id)], include=[])
    if not existing["ids"]:
        store_resume_embedding(
            resume_id=str(resume.id),
            text=resume.raw_text,
            metadata={
                "filename": resume.filename,
                "skills": ",".join(resume.parsed_data.get("skills", [])),
                "ats_score": str(resume.ats_score or 0)
            }
        )

    all_jobs_result = await db.execute(select(Job).where(Job.expires_at > datetime.utcnow()))
    all_jobs = all_jobs_result.scalars().all()
    active_job_ids = {str(job.id) for job in all_jobs}

    for job in all_jobs:
        existing_job = job_collection.get(ids=[str(job.id)], include=[])
        if not existing_job["ids"]:
            store_job_embedding(
                job_id=str(job.id),
                text=f"{job.title} {job.description}",
                metadata={
                    "title": job.title,
                    "company": job.company or "",
                    "skills": ",".join(job.required_skills or [])
                }
            )

    try:
        matches = match_resume_to_job(str(resume_id), top_k=max(5, len(active_job_ids)))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

    matches = [
        match for match in matches
        if match["job_id"] in active_job_ids
    ][:5]

    return {"resume_id": str(resume_id), "matches": matches}

@router.get("/gap/{resume_id}/{job_id}")
async def skill_gap(
    resume_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    resume_result = await db.execute(
        select(Resume).where(
            Resume.id == resume_id,
            Resume.user_id == current_user.id
        )
    )
    resume = resume_result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    job_result = await db.execute(
        select(Job).where(
            Job.id == job_id,
            Job.expires_at > datetime.utcnow()
        )
    )
    job = job_result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    resume_skills = resume.parsed_data.get("skills", [])
    job_skills = job.required_skills or []
    gap = compute_skill_gap(resume_skills, job_skills)

    return {
        "resume_id": str(resume_id),
        "job_id": str(job_id),
        "job_title": job.title,
        **gap
    }
