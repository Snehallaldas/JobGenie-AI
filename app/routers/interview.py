from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
import math
from app.database import get_db
from app.models.interview import InterviewSession
from app.models.resume import Resume
from app.models.job import Job
from app.models.user import User
from app.services.auth_service import get_current_user
from app.services.mistral_service import (
    generate_questions,
    evaluate_answer,
    generate_feedback_report
)

router = APIRouter()

SCORE_FIELDS = {
    "relevance_score": "relevance",
    "technical_depth_score": "technical_depth",
    "clarity_score": "clarity",
    "overall_score": "overall"
}


def _safe_score(value) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0

    if not math.isfinite(score):
        return 0

    return max(0, min(10, score))


def _sanitize_json(value):
    if isinstance(value, float):
        return value if math.isfinite(value) else 0
    if isinstance(value, dict):
        return {key: _sanitize_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_json(item) for item in value]
    return value


def _get_answer_payload(answer: dict | None) -> dict:
    if isinstance(answer, dict):
        return answer
    return {}


def _get_evaluation(answer: dict | None) -> dict:
    payload = _get_answer_payload(answer)
    evaluation = payload.get("evaluation")
    if isinstance(evaluation, dict):
        return evaluation
    return {}


def _get_score(answer: dict | None, score_field: str) -> float:
    return _safe_score(_get_evaluation(answer).get(score_field, 0))


def _get_feedback(answer: dict | None) -> str:
    feedback = _get_evaluation(answer).get("feedback", "")
    return feedback if isinstance(feedback, str) else ""


def _average_score(answers: list[dict], score_field: str) -> float:
    scores = [_get_score(answer, score_field) for answer in answers]
    return round(sum(scores) / len(scores), 2) if scores else 0


def _score_grade(score: float) -> str:
    if score >= 9:
        return "A"
    if score >= 8:
        return "B"
    if score >= 6:
        return "C"
    if score >= 4:
        return "D"
    return "F"


def _score_status(score: float) -> str:
    if score >= 8:
        return "strong"
    if score >= 6:
        return "needs practice"
    return "needs improvement"


def build_score_card(answers: list[dict], total_questions: int) -> dict:
    safe_answers = [_get_answer_payload(answer) for answer in answers]
    overall_score = _average_score(safe_answers, "overall_score")
    category_scores = {
        label: _average_score(safe_answers, field)
        for field, label in SCORE_FIELDS.items()
        if field != "overall_score"
    }
    question_scores = [
        {
            "question_index": answer.get("question_index"),
            "question": answer.get("question", ""),
            "overall_score": _get_score(answer, "overall_score"),
            "relevance_score": _get_score(answer, "relevance_score"),
            "technical_depth_score": _get_score(answer, "technical_depth_score"),
            "clarity_score": _get_score(answer, "clarity_score"),
            "feedback": _get_feedback(answer)
        }
        for answer in safe_answers
    ]

    # Ensure overall_score is safe before calculating percentage
    safe_overall_score = _safe_score(overall_score)
    score_percentage = round((safe_overall_score / 10) * 100, 2)

    return {
        "overall_score": safe_overall_score,
        "score_percentage": score_percentage,
        "grade": _score_grade(safe_overall_score),
        "status": _score_status(safe_overall_score),
        "answered_questions": len(safe_answers),
        "total_questions": total_questions,
        "category_scores": category_scores,
        "question_scores": question_scores
    }

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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    resume_result = await db.execute(
        select(Resume).where(
            Resume.id == request.resume_id,
            Resume.user_id == current_user.id
        )
    )
    resume = resume_result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    job_result = await db.execute(
        select(Job).where(
            Job.id == request.job_id,
            Job.expires_at > datetime.utcnow()
        )
    )
    job = job_result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    try:
        questions = generate_questions(
            resume_text=resume.raw_text,
            job_title=job.title,
            job_description=job.description,
            num_questions=request.num_questions
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Question generation failed: {str(e)}")

    session = InterviewSession(
        resume_id=request.resume_id,
        job_id=request.job_id,
        questions=questions,
        answers=[],
        status="in_progress",
        user_id=current_user.id
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    session_result = await db.execute(
        select(InterviewSession).where(
            InterviewSession.id == request.session_id,
            InterviewSession.user_id == current_user.id
        )
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

    job_result = await db.execute(select(Job).where(Job.id == session.job_id))
    job = job_result.scalar_one_or_none()

    try:
        evaluation = evaluate_answer(
            question=question["question"],
            answer=request.answer,
            expected_keywords=question.get("expected_keywords", []),
            job_title=job.title if job else "Software Engineer"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(e)}")

    answers = list(session.answers or [])
    answers.append({
        "question_index": request.question_index,
        "question": question["question"],
        "answer": request.answer,
        "evaluation": evaluation
    })

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
async def complete_interview(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    session_result = await db.execute(
        select(InterviewSession).where(
            InterviewSession.id == session_id,
            InterviewSession.user_id == current_user.id
        )
    )
    session = session_result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    answers = session.answers or []
    if not answers:
        raise HTTPException(status_code=400, detail="No answers submitted yet")

    answers = _sanitize_json(answers)
    score_card = build_score_card(answers, len(session.questions or []))
    average_score = score_card["overall_score"]

    performance_summary = "\n".join([
        f"Q{a['question_index']+1}: {a['question']}\n"
        f"Score: {_safe_score(a['evaluation'].get('overall_score', 0))}/10\n"
        f"Feedback: {a['evaluation'].get('feedback', '')}\n"
        for a in answers
    ])

    job_result = await db.execute(select(Job).where(Job.id == session.job_id))
    job = job_result.scalar_one_or_none()

    try:
        report = generate_feedback_report({
            "job_title": job.title if job else "Software Engineer",
            "average_score": average_score,
            "total_questions": len(answers),
            "performance_summary": performance_summary
        })
        report = _sanitize_json(report)
        report["score_card"] = score_card
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")

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
        "score_card": score_card,
        "report": report
    }

@router.get("/sessions")
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(InterviewSession).where(InterviewSession.user_id == current_user.id)
    )
    sessions = result.scalars().all()
    return [
        {
            "id": str(session.id),
            "resume_id": str(session.resume_id),
            "job_id": str(session.job_id),
            "status": session.status,
            "average_score": _safe_score(session.average_score),
            "report": _sanitize_json(session.report),
            "created_at": session.created_at,
            "completed_at": session.completed_at
        }
        for session in sessions
    ]


@router.get("/report/{session_id}")
async def get_report(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    session_result = await db.execute(
        select(InterviewSession).where(
            InterviewSession.id == session_id,
            InterviewSession.user_id == current_user.id
        )
    )
    session = session_result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Session not completed yet. Status: {session.status}"
        )

    answers = _sanitize_json(session.answers or [])
    report = _sanitize_json(session.report or {})
    score_card = build_score_card(answers, len(session.questions or []))
    report["score_card"] = score_card

    return {
        "session_id": str(session_id),
        "average_score": _safe_score(session.average_score),
        "score_card": score_card,
        "report": report,
        "answers": answers
    }
