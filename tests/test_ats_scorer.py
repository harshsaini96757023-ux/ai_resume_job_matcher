
from ats_scorer import score_resume


def test_ats_score_is_between_zero_and_hundred():
    result = score_resume("Python developer with SQL skills.")

    assert 0 <= result["score"] <= 100
    assert result["max_points"] == 100


def test_ats_detects_email_and_phone():
    resume = """
    Email: harsh@example.com
    Phone: +91 9876543210
    Skills: Python, SQL
    Education
    BCA
    """

    result = score_resume(resume)
    contact = result["checks"]["Contact Information"]

    assert contact["score"] == 20


def test_ats_detects_resume_sections():
    resume = """
    Professional Summary
    Python developer seeking an entry-level role.

    Skills
    Python, SQL, Django

    Education
    Bachelor of Computer Applications.

    Projects
    Developed a student management application.
    """

    result = score_resume(resume)

    assert "Skills" in result["sections_found"]
    assert "Education" in result["sections_found"]
    assert "Projects" in result["sections_found"]


def test_ats_returns_suggestions():
    result = score_resume("Python developer.")

    assert isinstance(result["suggestions"], list)
    assert len(result["suggestions"]) > 0
