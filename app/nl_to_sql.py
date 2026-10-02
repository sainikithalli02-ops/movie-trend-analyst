"""
The full question -> answer pipeline:

  1. interpret_question()  -- fix typos/grammar, resolve vague phrasing,
                               reject anything outside the schema's scope.
  2. _generate_sql()        -- Gemini turns the cleaned-up question into SQL.
  3. validate_and_prepare() -- guardrails: SELECT-only, single statement,
                               forced LIMIT, no destructive keywords.
  4. run_query()            -- executed against a read-only connection.

Every stage can fail independently and every failure mode returns a
normal NLToSQLResult with a plain-English `error` or `message` instead of
raising -- the UI never has to catch an exception to stay usable.
"""

import sys

from google.genai import types

from app.gemini_client import get_client, DEFAULT_MODEL, GeminiConfigError
from app.db import get_schema_description, run_query
from app.guardrails import validate_and_prepare, UnsafeSQLError
from app.interpreter import interpret_question, CAPABILITIES_BLURB  # noqa: F401 -- re-exported for the UI

SQL_SYSTEM_PROMPT = """You are a SQL assistant for a movie/TV trend-analytics database (SQLite dialect).

Schema:
{schema}

Rules: 
- Output ONLY a single SQL SELECT (or WITH ... SELECT) statement. No prose, no markdown fences, no explanation. 
- Use only tables/columns that appear in the schema above -- never invent a column. 
- Prefer window functions and CTEs where they make the query clearer. 
- For historical rating comparisons, use the available snapshot history in rating_snapshots. 
- When comparing the latest rating with the previous period, prefer LAG(rating) OVER (PARTITION BY movie_id ORDER BY snapshot_date). 
- Do not calculate a previous snapshot using DATE/DATETIME arithmetic and then require an exact date match. 
- For "trending", "rating increase", "momentum", or similar questions, calculate the change from the historical rating snapshots. 
- For questions asking for rating increase "this month", "latest", or the current trend, first identify the latest available snapshot for each movie, then compare it only with that movie's immediately preceding snapshot. 
- Do not return multiple historical rating changes for the same movie when the question asks for the current/latest rating increase. 
- Always include a LIMIT unless the question explicitly asks for every matching row. 
"""


class NLToSQLResult:
    """
    status is one of:
      "ok"             -- generated_sql / executed_sql / columns / rows are populated
      "cannot_answer"  -- the interpreter rejected the question; see `message`
      "error"          -- something failed (API, guardrails, DB); see `error`
    """

    def __init__(self, status, question=None, corrected_question=None,
                 was_corrected=False, message=None, generated_sql=None,
                 executed_sql=None, columns=None, rows=None, error=None):
        self.status = status
        self.question = question
        self.corrected_question = corrected_question
        self.was_corrected = was_corrected
        self.message = message
        self.generated_sql = generated_sql
        self.executed_sql = executed_sql
        self.columns = columns or []
        self.rows = rows or []
        self.error = error


def _generate_sql(question: str, schema: str) -> str:
    client = get_client()
    response = client.models.generate_content(
        model=DEFAULT_MODEL,
        contents=question,
        config=types.GenerateContentConfig(
            system_instruction=SQL_SYSTEM_PROMPT.format(schema=schema),
            temperature=0.1,
        ),
    )
    return (response.text or "").strip()


def ask(question: str, context: str = "") -> NLToSQLResult:
    """
    context: an optional short summary of recent conversation turns, so a
    follow-up like "no, I meant just the last 3 months" resolves against
    what was already discussed instead of being interpreted in isolation.
    """
    schema = get_schema_description()
    interpretation = interpret_question(question, schema, context=context)

    if interpretation.status == "error":
        return NLToSQLResult("error", question=question, error=interpretation.reason)

    if interpretation.status == "cannot_answer":
        return NLToSQLResult(
            "cannot_answer",
            question=question,
            corrected_question=interpretation.corrected_question,
            message=interpretation.reason or "I can't answer that from this dataset.",
        )

    corrected = interpretation.corrected_question

    try:
        raw_sql = _generate_sql(corrected, schema)
    except GeminiConfigError as e:
        return NLToSQLResult("error", question=question, corrected_question=corrected, error=str(e))
    except Exception as e:  # noqa: BLE001
        return NLToSQLResult("error", question=question, corrected_question=corrected,
                              error=f"Couldn't reach Gemini: {e}")

    if not raw_sql.strip():
        return NLToSQLResult(
            "cannot_answer", question=question, corrected_question=corrected,
            message="That resolved to a valid-sounding question, but I couldn't "
                    "turn it into a safe query against this schema. Try rephrasing it "
                    "more concretely (e.g. name a genre, platform, or time window).",
        )

    try:
        safe_sql = validate_and_prepare(raw_sql)
    except UnsafeSQLError as e:
        return NLToSQLResult("error", question=question, corrected_question=corrected,
                              generated_sql=raw_sql, error=f"Blocked by guardrails: {e}")

    try:
        columns, rows = run_query(safe_sql)
    except Exception as e:  # noqa: BLE001
        return NLToSQLResult("error", question=question, corrected_question=corrected,
                              generated_sql=raw_sql, executed_sql=safe_sql,
                              error=f"That query didn't run cleanly against the database: {e}")

    return NLToSQLResult(
        "ok",
        question=question,
        corrected_question=corrected,
        was_corrected=interpretation.was_corrected,
        generated_sql=raw_sql,
        executed_sql=safe_sql,
        columns=columns,
        rows=rows,
    )


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "Which unreviewed movies are trending up the most this month?"
    result = ask(q)
    print(f"Question: {result.question}")
    if result.was_corrected:
        print(f"Understood as: {result.corrected_question}")
    print(f"Status: {result.status}\n")
    if result.status == "cannot_answer":
        print(result.message)
    elif result.status == "error":
        print(f"Error: {result.error}")
    else:
        print(f"Generated SQL:\n{result.generated_sql}\n")
        print(f"Rows returned: {len(result.rows)}")

        for row in result.rows[:10]:
            print({
                key: round(value, 2) if isinstance(value, float) else value
                for key, value in row.items()
            })