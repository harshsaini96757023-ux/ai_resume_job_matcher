
import re
from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer


MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
SEMANTIC_THRESHOLD = 0.40

SKILLS = {
    "python", "sql", "mysql", "postgresql", "sqlite", "django",
    "fastapi", "flask", "pandas", "numpy", "excel", "power bi",
    "tableau", "html", "css", "javascript", "git", "github",
    "machine learning", "nlp", "data analysis", "streamlit",
    "scikit-learn", "rest api", "api", "data visualization",
    "statistics", "matplotlib", "plotly", "java", "c++", "c#",
    "aws", "docker", "linux", "mongodb", "data cleaning",
    "data analytics", "problem solving"
}


@lru_cache(maxsize=1)
def load_model():
    """Load the NLP model once and reuse it."""
    return SentenceTransformer(MODEL_NAME)


def extract_skills(text: str) -> set[str]:
    text = text.lower()
    found = set()

    for skill in SKILLS:
        pattern = r"(?<!\w)" + re.escape(skill) + r"(?!\w)"
        if re.search(pattern, text):
            found.add(skill)

    return found


def split_into_chunks(text: str, max_words: int = 60) -> list[str]:
    """Split text into manageable lines/sentences for semantic comparison."""
    chunks = []

    for line in text.splitlines():
        line = re.sub(r"^\s*[-*•\d.)]+\s*", "", line).strip()
        if not line:
            continue

        sentences = re.split(r"(?<=[.!?])\s+", line)

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence.split()) < 4:
                continue

            words = sentence.split()
            for start in range(0, len(words), max_words):
                chunk = " ".join(words[start:start + max_words]).strip()
                if len(chunk.split()) >= 4:
                    chunks.append(chunk)

    # Avoid excessive model processing on very long documents.
    return chunks[:80]


def analyze_match(resume_text: str, job_description: str) -> dict:
    resume_skills = extract_skills(resume_text)
    job_skills = extract_skills(job_description)

    matched_skills = sorted(resume_skills & job_skills)
    missing_skills = sorted(job_skills - resume_skills)

    resume_chunks = split_into_chunks(resume_text)
    job_chunks = split_into_chunks(job_description)

    if not resume_chunks:
        raise ValueError(
            "Could not split resume text into readable sentences."
        )

    if not job_chunks:
        raise ValueError(
            "Please provide a longer job description with responsibilities or requirements."
        )

    model = load_model()

    resume_embeddings = model.encode(
        resume_chunks,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    job_embeddings = model.encode(
        job_chunks,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )

    # Rows are resume chunks; columns are job requirements.
    similarities = np.matmul(resume_embeddings, job_embeddings.T)
    best_scores = similarities.max(axis=0)

    semantic_results = []
    for requirement, similarity in zip(job_chunks, best_scores):
        similarity_value = float(similarity)
        semantic_results.append({
            "requirement": requirement,
            "similarity": round(similarity_value * 100),
            "matched": similarity_value >= SEMANTIC_THRESHOLD,
        })

    semantic_matched = [
        item for item in semantic_results if item["matched"]
    ]
    semantic_missing = [
        item for item in semantic_results if not item["matched"]
    ]

    semantic_score = round(
        len(semantic_matched) / len(semantic_results) * 100
    )

    return {
        "score": semantic_score,
        "matched": matched_skills,
        "missing": missing_skills,
        "semantic_matched": semantic_matched,
        "semantic_missing": semantic_missing,
        "requirements_count": len(semantic_results),
        "threshold": SEMANTIC_THRESHOLD,
    }
