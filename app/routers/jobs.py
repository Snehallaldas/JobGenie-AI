from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from uuid import UUID
from typing import Optional
from datetime import datetime
import math
import traceback
from app.database import get_db
from app.models.job import Job
from app.models.resume import Resume
from app.models.user import User
from app.services.auth_service import get_current_user
from app.services.resume_parser import extract_skills
from app.services.embedding_service import (
    store_job_embedding,
    match_resume_to_job,
    compute_skill_gap,
    store_resume_embedding,
    resume_collection,
    job_collection
)

router = APIRouter()


def _safe_percentage(value) -> float:
    try:
        percentage = float(value)
    except (TypeError, ValueError):
        return 0

    if not math.isfinite(percentage):
        return 0

    return round(max(0, min(100, percentage)), 2)

class JobCreate(BaseModel):
    title: str
    company: Optional[str] = None
    description: str
    required_skills: list[str] = Field(default_factory=list)

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
    required_skills = job_data.required_skills or extract_skills(
        f"{job_data.title} {job_data.description}"
    )

    job = Job(
        title=job_data.title,
        company=job_data.company,
        description=job_data.description,
        required_skills=required_skills,
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
            "skills": ",".join(required_skills)
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
    active_jobs_by_id = {str(job.id): job for job in all_jobs}
    active_job_ids = set(active_jobs_by_id)
    if not active_job_ids:
        return {"resume_id": str(resume_id), "matches": []}

    for job in all_jobs:
        job_skills = job.required_skills or extract_skills(f"{job.title} {job.description}")
        if not job.required_skills and job_skills:
            job.required_skills = job_skills

        existing_job = job_collection.get(ids=[str(job.id)], include=[])
        if not existing_job["ids"]:
            store_job_embedding(
                job_id=str(job.id),
                text=f"{job.title} {job.description}",
                metadata={
                    "title": job.title,
                    "company": job.company or "",
                    "skills": ",".join(job_skills)
                }
            )

    await db.commit()

    try:
        matches = match_resume_to_job(str(resume_id), top_k=max(5, len(active_job_ids)))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

    enriched_matches = []
    resume_skills = resume.parsed_data.get("skills") or extract_skills(resume.raw_text)
    for match in matches:
        job = active_jobs_by_id.get(match["job_id"])
        if not job:
            continue

        job_skills = job.required_skills or extract_skills(f"{job.title} {job.description}")
        gap = compute_skill_gap(resume_skills, job_skills)
        semantic_score = _safe_percentage(match.get("similarity_score", 0))
        skill_score = _safe_percentage(gap["match_percentage"])
        final_score = _safe_percentage((semantic_score * 0.6) + (skill_score * 0.4))

        enriched_matches.append({
            **match,
            "similarity_score": final_score,
            "semantic_score": semantic_score,
            "skill_match_score": skill_score,
            "matched_skills": gap["matched_skills"],
            "missing_skills": gap["missing_skills"]
        })

    matches = sorted(
        enriched_matches,
        key=lambda item: item["similarity_score"],
        reverse=True
    )[:5]

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

    resume_skills = resume.parsed_data.get("skills") or extract_skills(resume.raw_text)
    job_skills = job.required_skills or extract_skills(f"{job.title} {job.description}")
    if not job.required_skills and job_skills:
        job.required_skills = job_skills
        await db.commit()

    gap = compute_skill_gap(resume_skills, job_skills)

    return {
        "resume_id": str(resume_id),
        "job_id": str(job_id),
        "job_title": job.title,
        **gap
    }
