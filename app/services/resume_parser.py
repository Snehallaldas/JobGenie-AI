import pdfplumber
import re

# Common skills keyword list; expand this as needed.
SKILLS_KEYWORDS = [
    "python", "java", "javascript", "react", "node.js", "fastapi",
    "django", "sql", "postgresql", "mongodb", "docker", "git",
    "machine learning", "deep learning", "nlp", "tensorflow", "pytorch",
    "aws", "gcp", "azure", "rest api", "html", "css", "typescript",
    "next.js", "express.js", "flask", "spring boot", "c++", "c#",
    "php", "laravel", "ruby", "rails", "golang", "rust",
    "kubernetes", "terraform", "jenkins", "github actions", "ci/cd",
    "mysql", "sqlite", "redis", "elasticsearch", "graphql", "grpc",
    "linux", "bash", "powershell", "data analysis", "pandas", "numpy",
    "scikit-learn", "opencv", "llm", "rag", "langchain", "chromadb",
    "prompt engineering", "tailwind", "bootstrap", "figma", "ui/ux"
]

SKILL_ALIASES = {
    "nodejs": "node.js",
    "node": "node.js",
    "reactjs": "react",
    "nextjs": "next.js",
    "express": "express.js",
    "postgres": "postgresql",
    "mongo": "mongodb",
    "k8s": "kubernetes",
    "ml": "machine learning",
    "ai": "machine learning",
    "genai": "llm",
    "generative ai": "llm",
    "large language models": "llm",
    "rest": "rest api",
    "apis": "rest api",
    "cicd": "ci/cd",
    "ci cd": "ci/cd",
    "sklearn": "scikit-learn",
    "ts": "typescript",
    "js": "javascript"
}

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


def normalize_skill(skill: str) -> str:
    normalized = re.sub(r"\s+", " ", skill.strip().lower())
    normalized = normalized.replace("node js", "node.js")
    normalized = normalized.replace("next js", "next.js")
    normalized = normalized.replace("express js", "express.js")
    normalized = normalized.replace("restful api", "rest api")
    return SKILL_ALIASES.get(normalized, normalized)


def extract_skills(text: str) -> list[str]:
    text_lower = text.lower()
    found = set()

    for skill in SKILLS_KEYWORDS:
        normalized_skill = normalize_skill(skill)
        pattern = r"(?<![a-z0-9+#.])" + re.escape(skill.lower()) + r"(?![a-z0-9+#.])"
        if re.search(pattern, text_lower):
            found.add(normalized_skill)

    for alias, canonical in SKILL_ALIASES.items():
        pattern = r"(?<![a-z0-9+#.])" + re.escape(alias) + r"(?![a-z0-9+#.])"
        if re.search(pattern, text_lower):
            found.add(canonical)

    return sorted(found)


def extract_sections(text: str) -> dict:
    """Detect which ATS sections are present in the resume."""
    text_lower = text.lower()
    found = {}
    for section in ATS_SECTIONS:
        found[section] = section in text_lower
    return found


def calculate_ats_score(parsed_data: dict) -> float:
    """
    ATS score out of 100 based on sections, skills, contact info, and length.
    """
    score = 0.0

    sections = parsed_data.get("sections", {})
    section_score = sum(1 for present in sections.values() if present)
    score += min(section_score * 5, 35)

    skills = parsed_data.get("skills", [])
    score += min(len(skills) * 3, 35)

    if parsed_data.get("email"):
        score += 8
    if parsed_data.get("phone"):
        score += 7

    word_count = parsed_data.get("word_count", 0)
    if 350 <= word_count <= 900:
        score += 15
    elif 200 <= word_count < 350 or 900 < word_count <= 1200:
        score += 10
    elif word_count >= 120:
        score += 5

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
