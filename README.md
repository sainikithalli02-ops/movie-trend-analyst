# TrendScout — AI-Powered SQL Analytics for "What Should We Cover Next?"

**Problem:** Content teams (and analysts everywhere) waste time writing one-off
SQL every time someone asks an ad-hoc question. TrendScout lets anyone ask in
plain English — *"Which unreviewed titles are trending up the most this
month?"* — and get back the exact SQL that answered it, executed safely
against a real relational database. No black box: the generated query is
always shown before the results.

**Key finding (on the seed dataset):** roughly 30% of titles show a genuine
multi-month upward rating trend rather than a single lucky spike — the
`04_consecutive_growth_streaks.sql` query is what separates "trending" from
"noisy."

## Why this exists

Most portfolio SQL projects are a single flat CSV and ten `SELECT` statements
against it. This one is built the way a real analytics problem actually
looks:

- A **normalized, relational schema** (movies / genres / platforms /
  monthly rating snapshots) — not one wide table.
- A **time series**, not a static snapshot, so month-over-month and
  streak-detection queries are possible at all.
- An **AI layer with guardrails**, not a raw "pipe user input into an LLM
  and eval() the output" toy: every generated query is validated (SELECT-only,
  single statement, forbidden-keyword check, forced `LIMIT`) and executed
  against a read-only connection before a result ever reaches the user.

## Data

- **Seed mode (default, no API key needed):** `data/generate_seed_data.py`
  builds a synthetic but structurally realistic dataset — 220 titles, 6
  months of rating history each — so the project runs immediately after
  cloning.
- **Real mode:** `data/fetch_tmdb_data.py` pulls live data from
  [TMDB](https://www.themoviedb.org/documentation/api) (free API key). Run it
  monthly to build up real `rating_snapshots` history — that history is what
  the trend queries depend on.

## SQL highlights (`db/queries/`)

| File | Technique |
|---|---|
| `01_trending_this_month.sql` | `LAG()` window function for month-over-month rating/vote delta |
| `02_genre_momentum.sql` | Aggregation + window function across a rollup |
| `03_unreviewed_high_potential.sql` | Anti-join (`NOT EXISTS`) to find content gaps |
| `04_consecutive_growth_streaks.sql` | Gaps-and-islands pattern to detect N-month consecutive streaks |

## AI layer (`app/`)

The pipeline is two LLM calls, not one, on purpose — the first call's whole
job is to catch problems before any SQL exists:

1. `app/db.py` introspects the live schema and opens a **read-only**
   connection.
2. `app/interpreter.py` sends the schema + the user's raw message to Gemini
   first, *before any SQL is written*. It silently fixes typos/grammar
   ("triming moveis" → "trending movies"), resolves vague phrasing into a
   specific question, and flags anything outside the schema's scope (plot
   details, actor bios, real-time news, requests to modify data) — so the
   user gets a clear explanation of what's answerable instead of a
   confusing SQL error three steps later.
3. `app/nl_to_sql.py` sends the *cleaned-up* question to Gemini asking for
   SQL only, then hands the result to guardrails.
4. `app/guardrails.py` validates the returned SQL before it's allowed to run
   — blocks anything that isn't a single `SELECT`/`WITH` statement, strips
   markdown fences, forces a row limit.
5. `app/streamlit_app.py` is the chat-style UI: every answer shows what was
   understood, the SQL that ran, and a 👍/👎 so a wrong answer leads
   straight into a follow-up instead of a dead end.

Every stage returns a plain result object with a status and message instead
of raising — an API outage, a malformed model response, or a genuinely
unanswerable question all produce a normal, readable answer in the UI, not
a stack trace. See `tests/test_pipeline.py` for the behavior this is meant
to guarantee (21 tests, all mocked — no API key needed to run them).

## Running it

```bash
git clone <this-repo>
cd movie-trend-analyst
pip install -r requirements.txt

cp .env.example .env        # then fill in GEMINI_API_KEY (free at aistudio.google.com/apikey)
python init_db.py           # builds trendscout.db from synthetic seed data

streamlit run app/streamlit_app.py
```

Or skip the UI and query straight from the CLI:

```bash
python -m app.nl_to_sql "Which genres gained the most average rating month over month?"
```

Run the test suite (no API key required — the Gemini client is mocked):

```bash
python -m unittest discover -s tests -v
```

## Limitations (said out loud, on purpose)

- The seed dataset is synthetic — real conclusions require running
  `fetch_tmdb_data.py` on a schedule to accumulate genuine rating history.
- The interpretation layer catches typos and obviously out-of-scope
  questions, but it's grounded in the schema, not fine-tuned — a genuinely
  ambiguous multi-hop question can still produce a SQL query that runs but
  isn't quite what was meant. That's exactly what the visible "here's what
  I understood" note and the 👍/👎 feedback loop are for.
- Guardrails block destructive/multi-statement SQL, but the read-only DB
  connection is the real safety net, not the regex checks alone.
- `gemini-flash-latest` (the default model alias) tracks Google's current
  best Flash model automatically; pin `GEMINI_MODEL` to a specific version
  if you need reproducible behavior across runs.

## Tech stack

SQLite · Python · Gemini API (`google-genai` SDK) · Streamlit · TMDB API
(for real data)
