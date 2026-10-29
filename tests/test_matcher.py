
from matcher import extract_skills, split_into_chunks


def test_extract_skills_finds_python_and_sql():
    text = "I build applications using Python and MySQL."
    skills = extract_skills(text)

    assert "python" in skills
    assert "mysql" in skills


def test_extract_skills_avoids_partial_word_matches():
    skills = extract_skills("I enjoy learning pythonista tools.")

    assert "python" not in skills


def test_split_into_chunks_returns_readable_text():
    text = (
        "Develop backend APIs using Python and FastAPI.\n"
        "Manage relational databases using SQL and MySQL."
    )

    chunks = split_into_chunks(text)

    assert len(chunks) >= 2
    assert any("FastAPI" in chunk for chunk in chunks)
    assert any("MySQL" in chunk for chunk in chunks)


def test_split_into_chunks_ignores_empty_text():
    assert split_into_chunks("") == []
