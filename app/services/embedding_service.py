import chromadb
import httpx
import math

from app.config import get_settings
from app.services.resume_parser import normalize_skill

settings = get_settings()

MISTRAL_EMBEDDINGS_URL = "https://api.mistral.ai/v1/embeddings"


def _collection_suffix() -> str:
    return settings.EMBEDDING_MODEL.replace("-", "_").replace(".", "_")


# Initialize ChromaDB persistent client.
chroma_client = chromadb.PersistentClient(
    path=settings.CHROMA_PERSIST_DIR
)

# Collections: one for resumes, one for job descriptions.
resume_collection = chroma_client.get_or_create_collection(
    name=f"resumes_{_collection_suffix()}",
    metadata={"hnsw:space": "cosine"}
)

job_collection = chroma_client.get_or_create_collection(
    name=f"job_descriptions_{_collection_suffix()}",
    metadata={"hnsw:space": "cosine"}
)


def embed_text(text: str) -> list[float]:
    """Convert any text into a vector embedding."""
    if not settings.MISTRAL_API_KEY:
        raise RuntimeError("MISTRAL_API_KEY is not configured")

    try:
        response = httpx.post(
            MISTRAL_EMBEDDINGS_URL,
            headers={
                "Authorization": f"Bearer {settings.MISTRAL_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"model": settings.EMBEDDING_MODEL, "input": text},
            timeout=60,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        raise RuntimeError(f"Mistral embeddings API error {exc.response.status_code}: {detail}") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Mistral embeddings API request failed: {exc}") from exc

    data = response.json().get("data", [])
    if not data:
        raise RuntimeError("Mistral embeddings API returned no embeddings")
    return data[0]["embedding"]


def store_resume_embedding(resume_id: str, text: str, metadata: dict) -> None:
    """Embed and store a resume in ChromaDB."""
    embedding = embed_text(text)
    resume_collection.upsert(
        ids=[resume_id],
        embeddings=[embedding],
        documents=[text],
        metadatas=[metadata]
    )


def store_job_embedding(job_id: str, text: str, metadata: dict) -> None:
    """Embed and store a job description in ChromaDB."""
    embedding = embed_text(text)
    job_collection.upsert(
        ids=[job_id],
        embeddings=[embedding],
        documents=[text],
        metadatas=[metadata]
    )


def _safe_percentage(value) -> float:
    try:
        percentage = float(value)
    except (TypeError, ValueError):
        return 0

    if not math.isfinite(percentage):
        return 0

    return round(max(0, min(100, percentage)), 2)


def match_resume_to_job(resume_id: str, top_k: int = 5) -> list[dict]:
    job_count = job_collection.count()
    if job_count == 0:
        return []

    result = resume_collection.get(
        ids=[resume_id],
        include=["embeddings"]
    )

    embeddings = result.get("embeddings")
    if embeddings is None or len(embeddings) == 0:
        raise ValueError(f"Resume {resume_id} not found in vector store")

    resume_embedding = embeddings[0]

    if hasattr(resume_embedding, "tolist"):
        resume_embedding = resume_embedding.tolist()

    matches = job_collection.query(
        query_embeddings=[resume_embedding],
        n_results=min(top_k, job_count),
        include=["documents", "metadatas", "distances"]
    )

    results = []
    for i in range(len(matches["ids"][0])):
        distance = matches["distances"][0][i]
        if hasattr(distance, "item"):
            distance = distance.item()
        similarity = _safe_percentage((1 - distance) * 100)
        results.append({
            "job_id": matches["ids"][0][i],
            "job_title": matches["metadatas"][0][i].get("title", "Unknown"),
            "similarity_score": similarity,
            "description": matches["documents"][0][i][:200] + "..."
        })

    return results


def compute_skill_gap(resume_skills: list[str], job_skills: list[str]) -> dict:
    """Compare resume skills against job required skills."""
    resume_set = {
        normalize_skill(skill)
        for skill in resume_skills
        if skill and normalize_skill(skill)
    }
    job_set = {
        normalize_skill(skill)
        for skill in job_skills
        if skill and normalize_skill(skill)
    }

    matched = resume_set.intersection(job_set)
    missing = job_set.difference(resume_set)
    extra = resume_set.difference(job_set)

    match_percentage = _safe_percentage(len(matched) / len(job_set) * 100) if job_set else 0

    return {
        "matched_skills": sorted(matched),
        "missing_skills": sorted(missing),
        "extra_skills": sorted(extra),
        "match_percentage": match_percentage
    }
