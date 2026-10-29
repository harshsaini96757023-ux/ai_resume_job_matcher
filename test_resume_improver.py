
import unittest

from resume_improver import extract_keywords, improve_resume


class TestResumeImprover(unittest.TestCase):

    def test_extract_keywords(self):
        job_description = (
            "Python developer with Django, SQL, Git and REST API skills"
        )

        keywords = extract_keywords(job_description)

        self.assertIn("python", keywords)
        self.assertIn("django", keywords)
        self.assertIn("sql", keywords)

    def test_missing_keywords(self):
        resume = "Developed a project using Python and SQL."
        job_description = (
            "Python developer with Django, SQL, Git and REST API skills"
        )

        result = improve_resume(resume, job_description)

        self.assertIn("django", result["missing_keywords"])
        self.assertIn("git", result["missing_keywords"])
        self.assertIn("rest api", result["missing_keywords"])

    def test_weak_phrases(self):
        resume = "Worked on a project. Responsible for data entry."
        job_description = "Python developer"

        result = improve_resume(resume, job_description)

        self.assertIn("worked on", result["weak_phrases"])
        self.assertIn("responsible for", result["weak_phrases"])

    def test_result_structure(self):
        result = improve_resume(
            "Developed a Python project with GitHub.",
            "Python developer"
        )

        self.assertIn("missing_keywords", result)
        self.assertIn("weak_phrases", result)
        self.assertIn("suggestions", result)
        self.assertIsInstance(result["suggestions"], list)


if __name__ == "__main__":
    unittest.main()
