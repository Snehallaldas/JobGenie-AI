from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings
from app.config import get_settings

settings = get_settings()

# Load model once at module level — don't reload on every request
model = SentenceTransformer(settings.EMBEDDING_MODEL)

# Initialize ChromaDB persistent client
chroma_client = chromadb.PersistentClient(
    path=settings.CHROMA_PERSIST_DIR
)

# Collections — one for resumes, one for job descriptions
resume_collection = chroma_client.get_or_create_collection(
    name="resumes",
    metadata={"hnsw:space": "cosine"}
)

job_collection = chroma_client.get_or_create_collection(
    name="job_descriptions",
    metadata={"hnsw:space": "cosine"}
)

def embed_text(text: str) -> list[float]:
    """Convert any text into a vector embedding."""
    return model.encode(text).tolist()

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

def match_resume_to_job(resume_id: str, top_k: int = 5) -> list[dict]:
    job_count = job_collection.count()
    if job_count == 0:
        return []

    # Get the resume embedding from ChromaDB
    result = resume_collection.get(
        ids=[resume_id],
        include=["embeddings"]
    )

    # Fix — handle both None and empty numpy array
    embeddings = result.get("embeddings")
    if embeddings is None or len(embeddings) == 0:
        raise ValueError(f"Resume {resume_id} not found in vector store")

    resume_embedding = embeddings[0]

    # Convert numpy array to plain Python list
    if hasattr(resume_embedding, 'tolist'):
        resume_embedding = resume_embedding.tolist()

    # Query job collection
    matches = job_collection.query(
        query_embeddings=[resume_embedding],
        n_results=min(top_k, job_count),
        include=["documents", "metadatas", "distances"]
    )

    results = []
    for i in range(len(matches["ids"][0])):
        distance = matches["distances"][0][i]
        if hasattr(distance, 'item'):
            distance = distance.item()
        similarity = round((1 - distance) * 100, 2)
        results.append({
            "job_id": matches["ids"][0][i],
            "job_title": matches["metadatas"][0][i].get("title", "Unknown"),
            "similarity_score": similarity,
            "description": matches["documents"][0][i][:200] + "..."
        })

    return results

def compute_skill_gap(resume_skills: list[str], job_skills: list[str]) -> dict:
    """Compare resume skills against job required skills."""
    resume_set = set(s.lower() for s in resume_skills)
    job_set = set(s.lower() for s in job_skills)

    matched = resume_set.intersection(job_set)
    missing = job_set.difference(resume_set)
    extra = resume_set.difference(job_set)

    match_percentage = round(len(matched) / len(job_set) * 100, 2) if job_set else 0

    return {
        "matched_skills": list(matched),
        "missing_skills": list(missing),
        "extra_skills": list(extra),
        "match_percentage": match_percentage
    }