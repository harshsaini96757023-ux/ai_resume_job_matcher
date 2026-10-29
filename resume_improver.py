
import re

WEAK_PHRASES = [
    "worked on",
    "responsible for",
    "helped with",
    "knowledge of",
    "familiar with",
    "made a project",
    "hardworking",
    "good communication skills",
]

ACTION_VERBS = [
    "developed",
    "built",
    "implemented",
    "automated",
    "analyzed",
    "designed",
    "optimized",
    "created",
]


def extract_keywords(job_description: str) -> set[str]:
    """Extract useful technical terms from a job description."""
    text = job_description.lower()

    known_keywords = [
        "python", "sql", "mysql", "django", "fastapi",
        "pandas", "numpy", "git", "github", "rest api",
        "docker", "pytest", "unit testing", "postgresql",
        "excel", "power bi", "data analysis", "machine learning",
    ]

    return {
        keyword
        for keyword in known_keywords
        if re.search(
            rf"(?<!\w){re.escape(keyword)}(?!\w)",
            text
        )
    }


def improve_resume(resume_text: str, job_description: str) -> dict:
    """Create transparent, rule-based resume improvement suggestions."""
    resume_lower = resume_text.lower()
    job_keywords = extract_keywords(job_description)

    missing_keywords = sorted(
        keyword
        for keyword in job_keywords
        if not re.search(
            rf"(?<!\w){re.escape(keyword)}(?!\w)",
            resume_lower
        )
    )

    weak_phrases_found = [
        phrase
        for phrase in WEAK_PHRASES
        if phrase in resume_lower
    ]

    suggestions = []

    if missing_keywords:
        suggestions.append(
            "Review these job keywords and add only those "
            "that genuinely match your skills: "
            + ", ".join(missing_keywords)
        )

    if weak_phrases_found:
        suggestions.append(
            "Improve vague wording where possible: "
            + ", ".join(weak_phrases_found)
        )

    if not re.search(r"\b(github|gitlab)\b", resume_lower):
        suggestions.append(
            "Consider adding a GitHub or GitLab link "
            "if you have a relevant public project."
        )

    if not re.search(r"\b(developed|built|implemented|created)\b", resume_lower):
        suggestions.append(
            "Describe projects using clear action verbs "
            "such as Developed, Built, or Implemented."
        )

    if not suggestions:
        suggestions.append(
            "No common issues detected by these basic rules. "
            "Review your resume manually for clarity and accuracy."
        )

    return {
        "missing_keywords": missing_keywords,
        "weak_phrases": weak_phrases_found,
        "suggestions": suggestions,
    }
