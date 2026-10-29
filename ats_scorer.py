
import re

SECTION_PATTERNS = {
    "Contact Information": [
        r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b",
        r"(?:\+?\d[\d\s().-]{8,}\d)",
    ],
    "Professional Summary": [
        r"\bprofessional summary\b",
        r"\bcareer summary\b",
        r"\bprofile summary\b",
        r"\bobjective\b",
        r"\bprofessional profile\b",
        r"\babout me\b",
    ],
    "Skills": [
        r"\bskills\b",
        r"\btechnical skills\b",
        r"\bcore competencies\b",
        r"\bkey skills\b",
    ],
    "Work Experience": [
        r"\bwork experience\b",
        r"\bprofessional experience\b",
        r"\bemployment history\b",
        r"\bwork history\b",
        r"\bexperience\b",
        r"\binternship\b",
    ],
    "Education": [
        r"\beducation\b",
        r"\bacademic background\b",
        r"\bqualifications\b",
    ],
    "Projects": [
        r"\bprojects\b",
        r"\bpersonal projects\b",
        r"\bacademic projects\b",
        r"\bkey projects\b",
    ],
}

ACTION_VERBS = {
    "built", "created", "developed", "designed", "implemented",
    "managed", "analyzed", "automated", "improved", "tested",
    "deployed", "optimized", "led", "maintained", "delivered",
}

def score_resume(resume_text: str) -> dict:
    """Return a transparent, rule-based resume quality estimate."""
    text = re.sub(r"\s+", " ", resume_text).strip()
    lower = text.lower()

    if not text:
        raise ValueError("Resume text is empty.")

    checks = {}
    suggestions = []

    # Contact details: 20 points
    email_found = bool(
        re.search(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b", text)
    )
    phone_found = bool(
        re.search(r"(?:\+?\d[\d\s().-]{8,}\d)", text)
    )
    contact_points = (10 if email_found else 0) + (
        10 if phone_found else 0
    )
    checks["Contact Information"] = {
        "score": contact_points,
        "max_score": 20,
        "details": (
            "Email found" if email_found else "Email not detected"
        ) + "; " + (
            "Phone number found" if phone_found
            else "Phone number not detected"
        ),
    }

    # Resume sections: 30 points
    section_points = 0
    section_results = {}

    for section, patterns in SECTION_PATTERNS.items():
        found = any(re.search(pattern, lower) for pattern in patterns)
        section_results[section] = found

    # Five main sections, 6 points each.
    main_sections = [
        "Professional Summary",
        "Skills",
        "Work Experience",
        "Education",
        "Projects",
    ]
    for section in main_sections:
        if section_results[section]:
            section_points += 6
        else:
            suggestions.append(
                f"Consider adding a clearly labelled {section} section if relevant."
            )

    checks["Resume Sections"] = {
        "score": section_points,
        "max_score": 30,
        "details": section_results,
    }

    # Relevant content length: 15 points
    word_count = len(text.split())
    if 250 <= word_count <= 1000:
        length_points = 15
        length_message = "Good text length"
    elif 150 <= word_count < 250 or 1000 < word_count <= 1500:
        length_points = 10
        length_message = "Acceptable text length"
    elif 80 <= word_count < 150 or 1500 < word_count <= 2200:
        length_points = 5
        length_message = "Consider improving resume length"
    else:
        length_points = 0
        length_message = "Resume may be too short or too long"

    checks["Content Length"] = {
        "score": length_points,
        "max_score": 15,
        "details": f"{word_count} words — {length_message}",
    }

    # Skills evidence: 15 points
    skill_terms = [
        "python", "sql", "mysql", "django", "fastapi", "flask",
        "pandas", "numpy", "excel", "power bi", "tableau",
        "javascript", "html", "css", "git", "github",
        "machine learning", "data analysis", "rest api",
        "communication", "problem solving",
    ]
    found_skills = sorted({
        skill for skill in skill_terms
        if re.search(
            r"(?<!\w)" + re.escape(skill) + r"(?!\w)", lower
        )
    })
    skills_points = min(15, len(found_skills) * 3)

    checks["Skills Evidence"] = {
        "score": skills_points,
        "max_score": 15,
        "details": found_skills,
    }

    if len(found_skills) < 3:
        suggestions.append(
            "Add relevant technical or professional skills you genuinely possess."
        )

    # Readability / achievement evidence: 20 points
    bullet_count = len(
        re.findall(r"(?m)^\s*(?:[-*•▪]|\d+[.)])\s+", resume_text)
    )
    action_verb_count = sum(
        1 for verb in ACTION_VERBS
        if re.search(r"\b" + re.escape(verb) + r"\b", lower)
    )
    readability_points = min(10, bullet_count * 2)
    achievement_points = min(10, action_verb_count * 2)

    checks["Readable Bullet Points"] = {
        "score": readability_points,
        "max_score": 10,
        "details": f"{bullet_count} bullet points detected",
    }
    checks["Action Verbs"] = {
        "score": achievement_points,
        "max_score": 10,
        "details": f"{action_verb_count} different action verbs detected",
    }

    if bullet_count < 3:
        suggestions.append(
            "Use concise bullet points to explain responsibilities and projects."
        )
    if action_verb_count < 3:
        suggestions.append(
            "Describe your actual work using action verbs such as developed, "
            "built, tested, or analyzed."
        )

    total_score = sum(item["score"] for item in checks.values())
    max_score = sum(item["max_score"] for item in checks.values())

    if not suggestions:
        suggestions.append(
            "Review the resume for accuracy and support achievements with "
            "specific results where possible."
        )

    return {
        "score": round(total_score / max_score * 100),
        "earned_points": total_score,
        "max_points": max_score,
        "word_count": word_count,
        "sections_found": [
            name for name, found in section_results.items() if found
        ],
        "skills_found": found_skills,
        "checks": checks,
        "suggestions": suggestions,
        "disclaimer": (
            "This is an estimated resume-quality score, not an actual "
            "ATS vendor score or a guarantee of job selection."
        ),
    }
