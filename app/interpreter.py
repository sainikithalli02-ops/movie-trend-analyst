"""
Stage 1 of the pipeline, run before any SQL is ever generated.

Its job is to figure out what the user actually meant:
  - Silently fix typos and grammar ("triming moveis genre" -> "trending
    movies by genre").
  - Resolve vague phrasing into a specific, schema-answerable question.
  - Recognize when a question genuinely can't be answered from this
    database (wrong topic, asks to modify data, isn't a real question at
    all) and say so clearly instead of letting a confused SQL query fail
    silently three steps later.

This is what lets the app handle "any kind of input" gracefully: the
worst case is a clear, specific explanation of what it can and can't do --
never a raw stack trace or a nonsense query.
"""

import json
import re

from google.genai import types

from app.gemini_client import get_client, DEFAULT_MODEL, GeminiConfigError

MAX_QUESTION_LENGTH = 500

CAPABILITIES_BLURB = (
    "**What I can answer** -- anything about the movies/shows in this "
    "database:\n"
    "- Rating and popularity trends over time (month-over-month, "
    "multi-month streaks)\n"
    "- Genre-level performance comparisons\n"
    "- Platform availability and content gaps (what's trending but not on "
    "a given platform)\n"
    "- Which titles haven't been reviewed by the channel yet\n\n"
    "**What I can't answer:**\n"
    "- Anything outside this dataset -- plot details, actor bios, "
    "real-time news, box office beyond budget/revenue\n"
    "- General chit-chat unrelated to the data\n"
    "- Requests to add, change, or delete data (this is read-only)"
)

INTERPRET_SYSTEM_PROMPT = """You are the understanding layer in front of a movie/TV analytics SQL assistant.

Database schema (SQLite):
{schema}

The user's message may contain typos, grammar mistakes, or vague phrasing.
Your job, in order:
1. Silently correct spelling/grammar and resolve the message into ONE clear,
   specific analytical question that could plausibly be answered with a SQL
   query against the schema above. Preserve the user's actual intent --
   don't invent a different question.
2. Decide whether that corrected question is answerable against this schema.

status = "cannot_answer" when the question:
  - asks about something not represented in the schema (plot, cast/actors,
    real-time news, box office beyond budget/revenue, etc.)
  - asks to insert/update/delete/modify data
  - is empty, gibberish, or not actually a question (pure small talk)

Important:
  - Questions about trends, rating changes, growth, momentum, or comparisons
    over time are answerable when the schema contains historical snapshot
    data such as rating_snapshots with rating and snapshot_date.
  - Do not reject a question merely because "trending" or "rating increase"
    is not a literal column name. These metrics can be calculated from the
    available historical data using SQL.
  - When historical snapshots exist, use them to answer month-over-month or
    latest-vs-previous-period questions.

Otherwise status = "ok".

Respond with ONLY a JSON object -- no markdown fences, no prose outside it --
with exactly these keys:
{{
  "status": "ok" | "cannot_answer",
  "corrected_question": "<cleaned-up question, or the original if nothing needed fixing>",
  "was_corrected": true | false,
  "reason": "<if cannot_answer, one short, friendly sentence explaining why; otherwise empty string>"
}}
"""


class Interpretation:
    def __init__(self, status: str, corrected_question: str,
                 was_corrected: bool, reason: str):
        self.status = status  # "ok" | "cannot_answer" | "error"
        self.corrected_question = corrected_question
        self.was_corrected = was_corrected
        self.reason = reason


def _extract_json(raw_text: str) -> dict:
    """
    Gemini is asked for clean JSON but models occasionally wrap it in
    markdown fences or add a stray sentence -- strip defensively rather
    than let a slightly-off response crash the whole request.
    """
    cleaned = (raw_text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        cleaned = match.group(0)
    return json.loads(cleaned)


def interpret_question(question: str, schema: str, context: str = "") -> Interpretation:
    """
    context: optional short summary of the last turn or two of conversation,
    so follow-ups like "no, I meant the last 3 months" resolve correctly.
    """
    question = (question or "").strip()

    if not question:
        return Interpretation(
            "cannot_answer", "", False,
            "That came through empty -- try typing a question about movie "
            "or show trends.",
        )
    if len(question) > MAX_QUESTION_LENGTH:
        return Interpretation(
            "cannot_answer", question, False,
            f"That's a lot of text for one question ({len(question)} "
            f"characters) -- try breaking it into one specific question.",
        )

    prompt_input = question if not context else f"Recent context: {context}\n\nNew message: {question}"

    try:
        client = get_client()
        response = client.models.generate_content(
            model=DEFAULT_MODEL,
            contents=prompt_input,
            config=types.GenerateContentConfig(
                system_instruction=INTERPRET_SYSTEM_PROMPT.format(schema=schema),
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )
        data = _extract_json(response.text)
        status = data.get("status") if data.get("status") in ("ok", "cannot_answer") else "ok"
        return Interpretation(
            status=status,
            corrected_question=(data.get("corrected_question") or question).strip(),
            was_corrected=bool(data.get("was_corrected")),
            reason=(data.get("reason") or "").strip(),
        )
    except GeminiConfigError as e:
        return Interpretation("error", question, False, str(e))
    except json.JSONDecodeError:
        # Model didn't return parseable JSON -- fail open: treat the raw
        # question as fine rather than blocking the user on our own parsing bug.
        return Interpretation("ok", question, False, "")
    except Exception as e:  # noqa: BLE001 -- surfaced to the UI, never swallowed
        return Interpretation("error", question, False, f"Couldn't reach Gemini: {e}")
