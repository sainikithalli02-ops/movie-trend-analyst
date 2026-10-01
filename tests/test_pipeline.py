"""
Tests the pipeline end to end with a FAKE Gemini client -- no real API key
or network access required. This checks the logic this project actually
owns (interpretation parsing, guardrails, orchestration, edge cases); it
does not check Gemini's own output quality, which you should spot-check
manually once you have a real key.

Run:
    python -m pytest tests/ -v
or, without pytest installed:
    python tests/test_pipeline.py
"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.append(str(Path(__file__).parent.parent))

from app import gemini_client  # noqa: E402
from app.guardrails import validate_and_prepare, UnsafeSQLError  # noqa: E402
from app.interpreter import interpret_question, _extract_json  # noqa: E402
import app.nl_to_sql as nl_to_sql  # noqa: E402
from app.nl_to_sql import ask  # noqa: E402


def fake_response(text: str):
    """Mimics the shape of a google-genai GenerateContentResponse enough
    for our code, which only reads `.text`."""
    r = MagicMock()
    r.text = text
    return r


class FakeClient:
    """Swap in canned responses per call, in order."""
    def __init__(self, responses):
        self._responses = list(responses)
        self.models = MagicMock()
        self.models.generate_content = MagicMock(side_effect=self._next)

    def _next(self, *args, **kwargs):
        return fake_response(self._responses.pop(0))


class TestGuardrails(unittest.TestCase):
    def test_allows_plain_select(self):
        self.assertIn("LIMIT", validate_and_prepare("SELECT * FROM movies"))

    def test_allows_cte(self):
        sql = "WITH x AS (SELECT 1) SELECT * FROM x"
        self.assertTrue(validate_and_prepare(sql).startswith("WITH"))

    def test_strips_markdown_fence(self):
        sql = "```sql\nSELECT * FROM movies LIMIT 5\n```"
        self.assertNotIn("```", validate_and_prepare(sql))

    def test_blocks_drop(self):
        with self.assertRaises(UnsafeSQLError):
            validate_and_prepare("DROP TABLE movies")

    def test_blocks_stacked_statements(self):
        with self.assertRaises(UnsafeSQLError):
            validate_and_prepare("SELECT * FROM movies; DROP TABLE movies;")

    def test_blocks_update(self):
        with self.assertRaises(UnsafeSQLError):
            validate_and_prepare("UPDATE movies SET title = 'x'")

    def test_does_not_duplicate_existing_limit(self):
        sql = validate_and_prepare("SELECT * FROM movies LIMIT 3")
        self.assertEqual(sql.upper().count("LIMIT"), 1)


class TestInterpreterJsonParsing(unittest.TestCase):
    def test_parses_clean_json(self):
        raw = '{"status": "ok", "corrected_question": "x", "was_corrected": false, "reason": ""}'
        self.assertEqual(_extract_json(raw)["status"], "ok")

    def test_strips_markdown_fence(self):
        raw = '```json\n{"status": "ok", "corrected_question": "x", "was_corrected": false, "reason": ""}\n```'
        self.assertEqual(_extract_json(raw)["status"], "ok")

    def test_strips_stray_prose_around_json(self):
        raw = 'Sure, here you go:\n{"status": "ok", "corrected_question": "x", "was_corrected": false, "reason": ""}\nhope that helps!'
        self.assertEqual(_extract_json(raw)["corrected_question"], "x")

    def test_raises_on_genuinely_broken_json(self):
        with self.assertRaises(json.JSONDecodeError):
            _extract_json("not json at all")


class TestInterpretQuestionEdgeCases(unittest.TestCase):
    def test_empty_input_is_cannot_answer_without_calling_api(self):
        result = interpret_question("   ", schema="CREATE TABLE movies (id INT)")
        self.assertEqual(result.status, "cannot_answer")

    def test_overlong_input_is_cannot_answer_without_calling_api(self):
        result = interpret_question("a" * 501, schema="CREATE TABLE movies (id INT)")
        self.assertEqual(result.status, "cannot_answer")

    @patch("app.interpreter.get_client")
    def test_malformed_json_fails_open_to_ok(self, mock_get_client):
        mock_get_client.return_value = FakeClient(["this is not json"])
        result = interpret_question("trending movies", schema="CREATE TABLE movies (id INT)")
        self.assertEqual(result.status, "ok")  # fails open rather than blocking the user

    @patch("app.interpreter.get_client")
    def test_typo_correction_flows_through(self, mock_get_client):
        canned = json.dumps({
            "status": "ok",
            "corrected_question": "trending movies this month",
            "was_corrected": True,
            "reason": "",
        })
        mock_get_client.return_value = FakeClient([canned])
        result = interpret_question("triming moveis", schema="CREATE TABLE movies (id INT)")
        self.assertTrue(result.was_corrected)
        self.assertEqual(result.corrected_question, "trending movies this month")

    @patch("app.interpreter.get_client")
    def test_out_of_scope_question_is_cannot_answer(self, mock_get_client):
        canned = json.dumps({
            "status": "cannot_answer",
            "corrected_question": "what's the weather in Mumbai",
            "was_corrected": False,
            "reason": "This database only covers movie/show ratings and platforms, not weather.",
        })
        mock_get_client.return_value = FakeClient([canned])
        result = interpret_question("whats weather in mumbai", schema="CREATE TABLE movies (id INT)")
        self.assertEqual(result.status, "cannot_answer")
        self.assertIn("weather", result.reason.lower())


@patch("app.nl_to_sql.get_schema_description", return_value="CREATE TABLE movies (id INT)")
class TestAskOrchestration(unittest.TestCase):
    """
    Patches app.nl_to_sql's imported names directly, since `ask()` calls
    interpret_question / _generate_sql / run_query / get_schema_description
    as names already bound in that module's namespace. get_schema_description
    is mocked at the class level so these tests never need a real database
    file on disk -- they're testing orchestration logic, not the DB.
    """

    @patch("app.nl_to_sql.run_query")
    @patch("app.nl_to_sql._generate_sql")
    @patch("app.nl_to_sql.interpret_question")
    def test_happy_path_returns_ok(self, mock_interpret, mock_generate, mock_run, mock_schema):
        mock_interpret.return_value = MagicMock(
            status="ok", corrected_question="trending movies", was_corrected=False, reason="",
        )
        mock_generate.return_value = "SELECT title FROM movies LIMIT 5"
        mock_run.return_value = (["title"], [{"title": "Shadow Signal"}])

        result = ask("trending movies")
        self.assertEqual(result.status, "ok")
        self.assertEqual(len(result.rows), 1)

    @patch("app.nl_to_sql.interpret_question")
    def test_cannot_answer_short_circuits_before_sql_generation(self, mock_interpret, mock_schema):
        mock_interpret.return_value = MagicMock(
            status="cannot_answer", corrected_question="weather", was_corrected=False,
            reason="Not in this dataset.",
        )
        with patch("app.nl_to_sql._generate_sql") as mock_generate:
            result = ask("what's the weather")
            mock_generate.assert_not_called()
        self.assertEqual(result.status, "cannot_answer")
        self.assertEqual(result.message, "Not in this dataset.")

    @patch("app.nl_to_sql._generate_sql")
    @patch("app.nl_to_sql.interpret_question")
    def test_unsafe_sql_is_blocked_not_executed(self, mock_interpret, mock_generate, mock_schema):
        mock_interpret.return_value = MagicMock(
            status="ok", corrected_question="delete everything", was_corrected=False, reason="",
        )
        mock_generate.return_value = "DROP TABLE movies"
        with patch("app.nl_to_sql.run_query") as mock_run:
            result = ask("delete everything")
            mock_run.assert_not_called()
        self.assertEqual(result.status, "error")
        self.assertIn("guardrails", result.error.lower())

    @patch("app.nl_to_sql.run_query")
    @patch("app.nl_to_sql._generate_sql")
    @patch("app.nl_to_sql.interpret_question")
    def test_db_failure_surfaces_as_error_not_crash(self, mock_interpret, mock_generate, mock_run, mock_schema):
        mock_interpret.return_value = MagicMock(
            status="ok", corrected_question="trending movies", was_corrected=False, reason="",
        )
        mock_generate.return_value = "SELECT * FROM nonexistent_table"
        mock_run.side_effect = Exception("no such table: nonexistent_table")

        result = ask("trending movies")
        self.assertEqual(result.status, "error")
        self.assertIn("no such table", result.error)

    @patch("app.nl_to_sql.interpret_question")
    def test_gemini_config_error_surfaces_cleanly(self, mock_interpret, mock_schema):
        mock_interpret.return_value = MagicMock(
            status="ok", corrected_question="trending movies", was_corrected=False, reason="",
        )
        with patch("app.nl_to_sql._generate_sql", side_effect=nl_to_sql.GeminiConfigError("no key set")):
            result = ask("trending movies")
        self.assertEqual(result.status, "error")
        self.assertIn("no key set", result.error)


if __name__ == "__main__":
    unittest.main(verbosity=2)
