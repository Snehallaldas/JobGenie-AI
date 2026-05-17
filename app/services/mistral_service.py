import json

import httpx
from app.config import get_settings

settings = get_settings()

MISTRAL_CHAT_URL = "https://api.mistral.ai/v1/chat/completions"


def _complete_chat(model: str, prompt: str) -> str:
    if not settings.MISTRAL_API_KEY:
        raise RuntimeError("MISTRAL_API_KEY is not configured")

    try:
        response = httpx.post(
            MISTRAL_CHAT_URL,
            headers={
                "Authorization": f"Bearer {settings.MISTRAL_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
            },
            timeout=60,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        raise RuntimeError(f"Mistral API error {exc.response.status_code}: {detail}") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Mistral API request failed: {exc}") from exc

    return response.json()["choices"][0]["message"]["content"]

def generate_questions(resume_text: str, job_title: str, job_description: str, num_questions: int = 5) -> list[dict]:
    """Generate interview questions based on resume and job description."""
    
    prompt = f"""You are an expert technical interviewer. Based on the resume and job description below, generate {num_questions} interview questions.

RESUME:
{resume_text[:2000]}

JOB TITLE: {job_title}
JOB DESCRIPTION: {job_description[:1000]}

Generate a mix of:
- Technical questions specific to their skills
- Behavioral questions based on their experience
- Job-specific questions based on the role

Respond ONLY with a JSON object, no other text:
{{
  "questions": [
  {{
    "question": "question text here",
    "type": "technical|behavioral|situational",
    "difficulty": "easy|medium|hard",
    "expected_keywords": ["keyword1", "keyword2"]
  }}
  ]
}}"""

    content = _complete_chat(settings.MISTRAL_LARGE_MODEL, prompt)
    # Handle both array and object responses
    parsed = json.loads(content)
    if isinstance(parsed, list):
        return parsed
    # Sometimes Mistral wraps in an object
    for key in parsed:
        if isinstance(parsed[key], list):
            return parsed[key]
    return []

def evaluate_answer(question: str, answer: str, expected_keywords: list[str], job_title: str) -> dict:
    """Evaluate a candidate's answer and return scores + feedback."""
    
    prompt = f"""You are an expert interviewer evaluating a candidate's answer for a {job_title} position.

QUESTION: {question}

CANDIDATE'S ANSWER: {answer}

EXPECTED KEYWORDS: {", ".join(expected_keywords)}

Evaluate the answer on these criteria and respond ONLY with JSON:
{{
  "relevance_score": <0-10>,
  "technical_depth_score": <0-10>,
  "clarity_score": <0-10>,
  "overall_score": <0-10>,
  "feedback": "detailed feedback here",
  "strengths": ["strength1", "strength2"],
  "improvements": ["improvement1", "improvement2"],
  "keywords_used": ["keywords from expected that were mentioned"]
}}"""

    content = _complete_chat(settings.MISTRAL_LARGE_MODEL, prompt)
    parsed = json.loads(content)
    return parsed

def generate_feedback_report(session_data: dict) -> dict:
    """Generate a final performance report with learning resources."""
    
    prompt = f"""You are a career coach generating a performance report for a candidate.

JOB TITLE: {session_data['job_title']}
AVERAGE SCORE: {session_data['average_score']}/10
QUESTIONS ANSWERED: {session_data['total_questions']}

PERFORMANCE SUMMARY:
{session_data['performance_summary']}

Generate a comprehensive report and respond ONLY with JSON:
{{
  "overall_assessment": "paragraph assessment here",
  "top_strengths": ["strength1", "strength2", "strength3"],
  "areas_to_improve": ["area1", "area2", "area3"],
  "learning_resources": [
    {{
      "topic": "topic name",
      "resource": "resource name",
      "url": "https://...",
      "type": "course|documentation|tutorial"
    }}
  ],
  "readiness_level": "not ready|needs work|almost ready|ready",
  "next_steps": ["step1", "step2", "step3"]
}}"""

    content = _complete_chat(settings.MISTRAL_SMALL_MODEL, prompt)
    return json.loads(content)
