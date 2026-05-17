import pdfplumber
import re
from pathlib import Path

nlp = None

def get_nlp():
    global nlp
    if nlp is None:
        import spacy

        nlp = spacy.load("en_core_web_sm")
    return nlp

# Common skills keyword list — expand this as needed
SKILLS_KEYWORDS = [
    "python", "java", "javascript", "react", "node.js", "fastapi",
    "django", "sql", "postgresql", "mongodb", "docker", "git",
    "machine learning", "deep learning", "nlp", "tensorflow", "pytorch",
    "aws", "gcp", "azure", "rest api", "html", "css", "typescript"
]

# ATS section headers to look for
ATS_SECTIONS = [
    "education", "experience", "skills", "projects",
    "certifications", "summary", "objective", "achievements"
]

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
    pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    match = re.search(pattern, text)
    return match.group(0) if match else None

def extract_phone(text: str) -> str | None:
    pattern = r'[\+\(]?[1-9][0-9 .\-\(\)]{8,}[0-9]'
    match = re.search(pattern, text)
    return match.group(0) if match else None

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

    # Sections — 5 points each, max 40
    sections = parsed_data.get("sections", {})
    section_score = sum(1 for present in sections.values() if present)
    score += min(section_score * 5, 40)

    # Skills — 2 points each, max 40
    skills = parsed_data.get("skills", [])
    score += min(len(skills) * 2, 40)

    # Contact info — 10 points each
    if parsed_data.get("email"):
        score += 10
    if parsed_data.get("phone"):
        score += 10

    return round(score, 2)

def parse_resume(text: str) -> dict:
    """Master function — runs all extraction and returns structured data."""
    doc = get_nlp()(text)

    # Extract named entities for name detection
    name = None
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            name = ent.text
            break

    parsed = {
        "name": name,
        "email": extract_email(text),
        "phone": extract_phone(text),
        "skills": extract_skills(text),
        "sections": extract_sections(text),
        "word_count": len(text.split()),
    }

    parsed["ats_score"] = calculate_ats_score(parsed)
    return parsed
