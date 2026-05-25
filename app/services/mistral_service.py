import json
import math
import re
import httpx
from app.config import get_settings

settings = get_settings()

MISTRAL_CHAT_URL = "https://api.mistral.ai/v1/chat/completions"
SCORE_FIELDS = ["relevance_score", "technical_depth_score", "clarity_score", "overall_score"]
MAX_RETRIES = 2


def _safe_score(value) -> int:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0

    if not math.isfinite(score):
        return 0

    return max(0, min(10, int(score)))


def _zero_evaluation(feedback: str) -> dict:
    return {
        "relevance_score": 0,
        "technical_depth_score": 0,
        "clarity_score": 0,
        "overall_score": 0,
        "feedback": feedback,
        "strengths": [],
        "improvements": [
            "Provide a complete and relevant answer",
            "Address the question directly"
        ],
        "keywords_used": []
    }


def _is_low_quality_answer(answer: str, expected_keywords: list[str] | None = None) -> bool:
    normalized_answer = answer.strip()
    if not normalized_answer:
        return True

    words = re.findall(r"[A-Za-z0-9]+", normalized_answer.lower())
    if not words:
        return True

    normalized_keywords = {keyword.lower() for keyword in (expected_keywords or []) if keyword}
    keyword_match = any(keyword in normalized_answer.lower() for keyword in normalized_keywords)
    has_substantial_word = any(len(word) >= 4 for word in words)

    if keyword_match:
        return False

    if len(words) < 3:
        return True

    if not has_substantial_word:
        return True

    if len(set(words)) < 2:
        return True

    letters = "".join(words)
    if len(letters) < 8:
        return True

    vowel_count = sum(1 for char in letters if char in "aeiou")
    vowel_ratio = vowel_count / len(letters)
    return vowel_ratio < 0.12 and len(words) < 8


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


def generate_questions(
    resume_text: str,
    job_title: str,
    job_description: str
) -> list[dict]:
    """Generate interview questions based on resume and job description."""

    prompt = f"""You are an expert technical interviewer. Based on the resume and job description below, generate an appropriate number of interview questions as you see fit.

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
    parsed = json.loads(content)

    questions = []
    if isinstance(parsed, list):
        questions = parsed
    else:
        for key in parsed:
            if isinstance(parsed[key], list):
                questions = parsed[key]
                break

    # Ensure each question has required fields
    sanitized = []
    for q in questions:
        sanitized.append({
            "question": q.get("question", "Tell me about yourself."),
            "type": q.get("type", "general"),
            "difficulty": q.get("difficulty", "medium"),
            "expected_keywords": q.get("expected_keywords", [])
        })

    return sanitized


def _validate_evaluation_response(parsed: dict) -> bool:
    """Validate that the API response has all required score fields."""
    required_fields = ["relevance_score", "technical_depth_score", "clarity_score", "overall_score"]
    
    for field in required_fields:
        if field not in parsed:
            return False
        value = parsed[field]
        # Check if value is a valid number
        try:
            score = float(value)
            if not math.isfinite(score):
                return False
        except (TypeError, ValueError):
            return False
    
    return True


def _sanitize_feedback_arrays(data: dict) -> dict:
    """Ensure feedback arrays are valid lists of non-empty strings."""
    if not isinstance(data.get("strengths"), list):
        data["strengths"] = []
    else:
        # Filter out empty/non-string items
        data["strengths"] = [str(s).strip() for s in data["strengths"] if s and isinstance(s, (str, int, float))][:5]
    
    if not isinstance(data.get("improvements"), list):
        data["improvements"] = []
    else:
        # Filter out empty/non-string items
        data["improvements"] = [str(i).strip() for i in data["improvements"] if i and isinstance(i, (str, int, float))][:5]
    
    if not isinstance(data.get("keywords_used"), list):
        data["keywords_used"] = []
    else:
        # Filter out empty/non-string items
        data["keywords_used"] = [str(k).strip() for k in data["keywords_used"] if k and isinstance(k, (str, int, float))][:10]
    
    return data


def evaluate_answer(
    question: str,
    answer: str,
    expected_keywords: list[str],
    job_title: str
) -> dict:
    """Evaluate a candidate's answer and return scores + feedback."""

    if _is_low_quality_answer(answer, expected_keywords):
        return _zero_evaluation(
            "Answer appears incomplete, random, or unrelated. Please provide a meaningful response."
        )

    prompt = f"""You are an expert interviewer evaluating a candidate's answer for a {job_title} position.

QUESTION: {question}

CANDIDATE'S ANSWER: {answer}

EXPECTED KEYWORDS: {", ".join(expected_keywords) if expected_keywords else "N/A"}

IMPORTANT SCORING RULES:
- If the answer is random text, gibberish, or completely irrelevant, score 0-2
- If the answer is vague but somewhat related, score 3-5
- If the answer is good but incomplete, score 6-7
- Only score 8-10 for excellent, detailed, relevant answers
- All scores MUST be integers between 0 and 10
- Return ONLY valid JSON with no extra text
- CRITICAL: strengths, improvements, and keywords_used MUST be non-empty lists of strings when provided

Evaluate the answer and respond ONLY with JSON:
{{
  "relevance_score": <integer 0-10>,
  "technical_depth_score": <integer 0-10>,
  "clarity_score": <integer 0-10>,
  "overall_score": <integer 0-10>,
  "feedback": "detailed feedback here",
  "strengths": ["strength1", "strength2"],
  "improvements": ["improvement1", "improvement2"],
  "keywords_used": ["keywords from expected that were mentioned"]
}}"""

    # Retry logic for API calls
    for attempt in range(MAX_RETRIES + 1):
        try:
            content = _complete_chat(settings.MISTRAL_LARGE_MODEL, prompt)
            
            # Try to parse and validate JSON
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError as e:
                if attempt < MAX_RETRIES:
                    continue
                # If last attempt failed, return zero evaluation
                return _zero_evaluation(
                    f"Failed to parse evaluation response. Please try again."
                )
            
            # Validate response has all required fields
            if not _validate_evaluation_response(parsed):
                if attempt < MAX_RETRIES:
                    continue
                # If validation failed after retries, return zero evaluation
                return _zero_evaluation(
                    "Evaluation response was incomplete or invalid."
                )
            
            # Convert all scores to safe integers
            for field in SCORE_FIELDS:
                parsed[field] = _safe_score(parsed.get(field, 0))
            
            # Ensure all required fields exist with safe defaults
            parsed.setdefault("feedback", "No feedback provided.")
            parsed.setdefault("strengths", [])
            parsed.setdefault("improvements", [])
            parsed.setdefault("keywords_used", [])
            
            # Sanitize and validate feedback arrays
            parsed = _sanitize_feedback_arrays(parsed)
            
            return parsed
            
        except RuntimeError as e:
            if attempt < MAX_RETRIES:
                continue
            # If API call fails after retries, return zero evaluation
            return _zero_evaluation(
                f"Unable to evaluate answer due to service error: {str(e)}"
            )
    
    # Fallback (should not reach here)
    return _zero_evaluation("Evaluation service unavailable. Please try again.")


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

    try:
        content = _complete_chat(settings.MISTRAL_SMALL_MODEL, prompt)
        parsed = json.loads(content)
    except (RuntimeError, json.JSONDecodeError) as e:
        # Return a safe default report if API fails
        return {
            "overall_assessment": "Unable to generate assessment at this time.",
            "top_strengths": [],
            "areas_to_improve": [],
            "learning_resources": [],
            "readiness_level": "needs work",
            "next_steps": ["Review the feedback from individual answers above"]
        }

    # Ensure all required fields exist with safe defaults
    parsed.setdefault("overall_assessment", "No assessment provided.")
    parsed.setdefault("top_strengths", [])
    parsed.setdefault("areas_to_improve", [])
    parsed.setdefault("learning_resources", [])
    parsed.setdefault("readiness_level", "needs work")
    parsed.setdefault("next_steps", [])
    
    # Sanitize list fields
    if not isinstance(parsed["top_strengths"], list):
        parsed["top_strengths"] = []
    if not isinstance(parsed["areas_to_improve"], list):
        parsed["areas_to_improve"] = []
    if not isinstance(parsed["next_steps"], list):
        parsed["next_steps"] = []
    if not isinstance(parsed["learning_resources"], list):
        parsed["learning_resources"] = []

    return parsed

def elaborate_resume(resume_text: str) -> str:
    """Generate a detailed elaboration/summary of the resume."""
    prompt = f"""You are an expert career counselor. Please provide a detailed elaboration and professional summary of the following resume. Highlight the candidate's core strengths, major achievements, and the type of roles they are best suited for. Keep the tone encouraging and professional.

RESUME:
{resume_text[:4000]}

Respond ONLY with the elaboration text. Do not include any JSON or markdown formatting other than basic paragraphs.
"""
    try:
        content = _complete_chat(settings.MISTRAL_LARGE_MODEL, prompt)
        return content.strip()
    except Exception as e:
        return "Unable to elaborate on the resume at this time due to an error."

