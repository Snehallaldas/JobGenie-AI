from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from app.database import get_db
from app.models.interview import InterviewSession
from app.models.resume import Resume
from app.models.job import Job
from app.services.mistral_service import (
    generate_questions,
    evaluate_answer,
    generate_feedback_report
)

router = APIRouter()

class StartInterviewRequest(BaseModel):
    resume_id: UUID
    job_id: UUID
    num_questions: int = 5

class SubmitAnswerRequest(BaseModel):
    session_id: UUID
    question_index: int
    answer: str

@router.post("/start")
async def start_interview(
    request: StartInterviewRequest,
    db: AsyncSession = Depends(get_db)
):
    """Start an interview session — generates questions from resume + job."""

    # Fetch resume
    resume_result = await db.execute(select(Resume).where(Resume.id == request.resume_id))
    resume = resume_result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    # Fetch job
    job_result = await db.execute(select(Job).where(Job.id == request.job_id))
    job = job_result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Generate questions via Mistral
    try:
        questions = generate_questions(
            resume_text=resume.raw_text,
            job_title=job.title,
            job_description=job.description,
            num_questions=request.num_questions
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Question generation failed: {str(e)}")

    # Create session
    session = InterviewSession(
        resume_id=request.resume_id,
        job_id=request.job_id,
        questions=questions,
        answers=[],
        status="in_progress"
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return {
        "session_id": session.id,
        "job_title": job.title,
        "total_questions": len(questions),
        "questions": [
            {
                "index": i,
                "question": q["question"],
                "type": q.get("type", "general"),
                "difficulty": q.get("difficulty", "medium")
            }
            for i, q in enumerate(questions)
        ]
    }

@router.post("/answer")
async def submit_answer(
    request: SubmitAnswerRequest,
    db: AsyncSession = Depends(get_db)
):
    """Submit an answer to a question — evaluates and scores it."""

    session_result = await db.execute(
        select(InterviewSession).where(InterviewSession.id == request.session_id)
    )
    session = session_result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status == "completed":
        raise HTTPException(status_code=400, detail="Session already completed")

    questions = session.questions
    if request.question_index >= len(questions):
        raise HTTPException(status_code=400, detail="Invalid question index")

    question = questions[request.question_index]

    # Fetch job title for context
    job_result = await db.execute(select(Job).where(Job.id == session.job_id))
    job = job_result.scalar_one_or_none()

    # Evaluate answer via Mistral
    try:
        evaluation = evaluate_answer(
            question=question["question"],
            answer=request.answer,
            expected_keywords=question.get("expected_keywords", []),
            job_title=job.title if job else "Software Engineer"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(e)}")

    # Store answer + evaluation
    answers = list(session.answers or [])
    answers.append({
        "question_index": request.question_index,
        "question": question["question"],
        "answer": request.answer,
        "evaluation": evaluation
    })

    # Update session
    from sqlalchemy import update
    await db.execute(
        update(InterviewSession)
        .where(InterviewSession.id == request.session_id)
        .values(answers=answers)
    )
    await db.commit()

    return {
        "question_index": request.question_index,
        "question": question["question"],
        "evaluation": evaluation
    }

@router.post("/complete/{session_id}")
async def complete_interview(session_id: UUID, db: AsyncSession = Depends(get_db)):
    """Complete the session and generate the full performance report."""

    session_result = await db.execute(
        select(InterviewSession).where(InterviewSession.id == session_id)
    )
    session = session_result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    answers = session.answers or []
    if not answers:
        raise HTTPException(status_code=400, detail="No answers submitted yet")

    # Calculate average score
    scores = [a["evaluation"].get("overall_score", 0) for a in answers]
    average_score = round(sum(scores) / len(scores), 2)

    # Build performance summary for Mistral
    performance_summary = "\n".join([
        f"Q{a['question_index']+1}: {a['question']}\n"
        f"Score: {a['evaluation'].get('overall_score', 0)}/10\n"
        f"Feedback: {a['evaluation'].get('feedback', '')}\n"
        for a in answers
    ])

    # Fetch job
    job_result = await db.execute(select(Job).where(Job.id == session.job_id))
    job = job_result.scalar_one_or_none()

    # Generate report via Mistral
    try:
        report = generate_feedback_report({
            "job_title": job.title if job else "Software Engineer",
            "average_score": average_score,
            "total_questions": len(answers),
            "performance_summary": performance_summary
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")

    # Save completed session
    from sqlalchemy import update
    await db.execute(
        update(InterviewSession)
        .where(InterviewSession.id == session_id)
        .values(
            status="completed",
            average_score=average_score,
            report=report,
            completed_at=datetime.utcnow()
        )
    )
    await db.commit()

    return {
        "session_id": str(session_id),
        "average_score": average_score,
        "total_questions": len(answers),
        "report": report
    }

@router.get("/report/{session_id}")
async def get_report(session_id: UUID, db: AsyncSession = Depends(get_db)):
    """Fetch the full report for a completed session."""

    session_result = await db.execute(
        select(InterviewSession).where(InterviewSession.id == session_id)
    )
    session = session_result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Session not completed yet. Status: {session.status}"
        )

    return {
        "session_id": str(session_id),
        "average_score": session.average_score,
        "report": session.report,
        "answers": session.answers
    }