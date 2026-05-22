import pdfplumber
import re

# Common skills keyword list; expand this as needed.
SKILLS_KEYWORDS = [
    "python", "java", "javascript", "react", "node.js", "fastapi",
    "django", "sql", "postgresql", "mongodb", "docker", "git",
    "machine learning", "deep learning", "nlp", "tensorflow", "pytorch",
    "aws", "gcp", "azure", "rest api", "html", "css", "typescript"
]

# ATS section headers to look for.
ATS_SECTIONS = [
    "education", "experience", "skills", "projects",
    "certifications", "summary", "objective", "achievements"
]
SECTION_HEADERS = set(ATS_SECTIONS)


def extract_text_from_pdf(file_path: str) -> str:
    """Extract raw text from a PDF file."""
    text = ""
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text.strip()


def extract_email(text: str) -> str | None:
    pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    match = re.search(pattern, text)
    return match.group(0) if match else None


def extract_phone(text: str) -> str | None:
    pattern = r"[\+\(]?[1-9][0-9 .\-\(\)]{8,}[0-9]"
    match = re.search(pattern, text)
    return match.group(0) if match else None


def extract_name(text: str) -> str | None:
    """Best-effort name detection without a heavyweight NLP model."""
    for line in text.splitlines()[:12]:
        candidate = re.sub(r"\s+", " ", line).strip(" -|")
        if not candidate:
            continue

        candidate_lower = candidate.lower().rstrip(":")
        if candidate_lower in SECTION_HEADERS:
            continue
        if extract_email(candidate) or extract_phone(candidate):
            continue
        if any(char.isdigit() for char in candidate):
            continue

        words = candidate.split()
        if 2 <= len(words) <= 5 and all(re.match(r"^[A-Za-z][A-Za-z'.-]*$", word) for word in words):
            return candidate

    return None


def extract_skills(text: str) -> list[str]:
    text_lower = text.lower()
    found = [skill for skill in SKILLS_KEYWORDS if skill in text_lower]
    return list(set(found))


def extract_sections(text: str) -> dict:
    """Detect which ATS sections are present in the resume."""
    text_lower = text.lower()
    found = {}
    for section in ATS_SECTIONS:
        found[section] = section in text_lower
    return found


def calculate_ats_score(parsed_data: dict) -> float:
    """
    Simple ATS score out of 100 based on:
    - Sections present (40 points)
    - Skills found (40 points)
    - Contact info (20 points)
    """
    score = 0.0

    sections = parsed_data.get("sections", {})
    section_score = sum(1 for present in sections.values() if present)
    score += min(section_score * 5, 40)

    skills = parsed_data.get("skills", [])
    score += min(len(skills) * 2, 40)

    if parsed_data.get("email"):
        score += 10
    if parsed_data.get("phone"):
        score += 10

    return round(score, 2)


def parse_resume(text: str) -> dict:
    """Master function: runs all extraction and returns structured data."""
    parsed = {
        "name": extract_name(text),
        "email": extract_email(text),
        "phone": extract_phone(text),
        "skills": extract_skills(text),
        "sections": extract_sections(text),
        "word_count": len(text.split()),
    }

    parsed["ats_score"] = calculate_ats_score(parsed)
    return parsed
