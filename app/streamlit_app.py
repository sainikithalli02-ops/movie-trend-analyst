"""
TrendScout -- chat-style UI.

Design choices worth noting in an interview:
  - A chat interface (not a single text box + button) is what makes the
    "ask again / clarify / follow up" loop feel native instead of bolted on.
  - Every assistant turn shows *what it understood* before showing results,
    so a corrected typo is never a silent surprise.
  - Feedback (was this right?) is a first-class part of every answer, not
    an afterthought -- it's how the app invites a follow-up instead of
    just stopping.

Run:
    streamlit run app/streamlit_app.py
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.append(str(Path(__file__).parent.parent))
from app.nl_to_sql import ask, CAPABILITIES_BLURB  # noqa: E402
from app.gemini_client import DEFAULT_MODEL  # noqa: E402

st.set_page_config(page_title="TrendScout", page_icon="🎬", layout="centered")

# ------------------------------------------------------------------
# Styling -- dark, cinematic theme. Everything below is CSS only;
# no behavior lives in this block.
# ------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700;800&family=Inter:wght@400;500;600&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
h1, h2, h3, .ts-hero-title { font-family: 'Sora', sans-serif; }

.stApp {
    background:
        radial-gradient(circle at 15% 0%, rgba(212, 160, 60, 0.10), transparent 45%),
        radial-gradient(circle at 85% 10%, rgba(120, 70, 200, 0.12), transparent 40%),
        linear-gradient(180deg, #0b0c14 0%, #0e0f1a 100%);
}

/* ---- Hero header ---- */
.ts-hero {
    padding: 1.6rem 1.8rem;
    border-radius: 20px;
    margin-bottom: 1.4rem;
    background: linear-gradient(135deg, rgba(120,70,200,0.18), rgba(212,160,60,0.10));
    border: 1px solid rgba(255,255,255,0.08);
    box-shadow: 0 8px 32px rgba(0,0,0,0.35);
    animation: ts-fade-in 0.5s ease-out;
}
.ts-hero-title {
    font-size: 2.1rem;
    font-weight: 800;
    margin: 0;
    background: linear-gradient(90deg, #f4d58d, #e0b3ff 70%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}
.ts-hero-sub { color: #b7b9c8; font-size: 0.98rem; margin-top: 0.4rem; line-height: 1.5; }
.ts-badges { margin-top: 0.8rem; }
.ts-badge {
    display: inline-block;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    padding: 0.28rem 0.7rem;
    border-radius: 999px;
    margin-right: 0.4rem;
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.10);
    color: #d8d9e6;
}

/* ---- Chat bubbles ---- */
[data-testid="stChatMessage"] {
    border-radius: 16px;
    padding: 0.25rem 0.4rem;
    animation: ts-fade-in 0.35s ease-out;
}

/* ---- Understood-as note ---- */
.ts-understood {
    font-size: 0.85rem;
    color: #f4d58d;
    background: rgba(244, 213, 141, 0.08);
    border-left: 3px solid #f4d58d;
    padding: 0.45rem 0.7rem;
    border-radius: 6px;
    margin-bottom: 0.6rem;
}

/* ---- Cannot-answer note ---- */
.ts-cannot {
    font-size: 0.9rem;
    background: rgba(255, 99, 99, 0.08);
    border-left: 3px solid #ff6363;
    padding: 0.6rem 0.8rem;
    border-radius: 6px;
}

/* ---- Buttons ---- */
.stButton>button {
    border-radius: 10px;
    border: 1px solid rgba(255,255,255,0.12);
    transition: all 0.15s ease;
}
.stButton>button:hover {
    transform: translateY(-1px);
    border-color: #d4a03c;
    box-shadow: 0 4px 14px rgba(212,160,60,0.25);
}

/* ---- Code blocks ---- */
.stCodeBlock { animation: ts-fade-in 0.3s ease-out; border-radius: 12px !important; }

/* ---- Dataframe ---- */
[data-testid="stDataFrame"] {
    border-radius: 12px;
    overflow: hidden;
    animation: ts-fade-in 0.4s ease-out;
}

/* ---- Example chips ---- */
.ts-chip-row { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.6rem; }

@keyframes ts-fade-in {
    from { opacity: 0; transform: translateY(6px); }
    to   { opacity: 1; transform: translateY(0); }
}
</style>
""", unsafe_allow_html=True)

EXAMPLES = [
    "Which unreviewed movies are trending up the most this month?",
    "Which genres gained the most average rating month over month?",
    "Show me high-rated titles not yet on Netflix or Prime Video.",
    "Movies that grew in rating for 3+ months straight",
]

# ------------------------------------------------------------------
# Session state
# ------------------------------------------------------------------
if "turns" not in st.session_state:
    st.session_state.turns = []  # list of dicts: {question, result, feedback}
if "pending_question" not in st.session_state:
    st.session_state.pending_question = None


def _recent_context(max_turns: int = 2) -> str:
    """Summarizes the last couple of turns so follow-ups resolve correctly."""
    recent = st.session_state.turns[-max_turns:]
    if not recent:
        return ""
    parts = []
    for t in recent:
        r = t["result"]
        parts.append(f"Q: {t['question']} -> understood as: {r.corrected_question} (status: {r.status})")
    return " | ".join(parts)


def _run_turn(question: str):
    context = _recent_context()
    with st.spinner("Reading the question, then the data..."):
        result = ask(question, context=context)
    st.session_state.turns.append({"question": question, "result": result, "feedback": None})


def _render_result(idx: int, result):
    if result.status == "error":
        st.error(result.error)
        if result.generated_sql:
            with st.expander("Generated SQL (query was not run)"):
                st.code(result.generated_sql, language="sql")
        return

    if result.was_corrected and result.corrected_question:
        st.markdown(
            f'<div class="ts-understood">Here\'s what I understood: '
            f'<strong>{result.corrected_question}</strong></div>',
            unsafe_allow_html=True,
        )

    if result.status == "cannot_answer":
        st.markdown(f'<div class="ts-cannot">{result.message}</div>', unsafe_allow_html=True)
        with st.expander("What can TrendScout answer?"):
            st.markdown(CAPABILITIES_BLURB)
        return

    # status == "ok"
    st.success(f"{len(result.rows)} row{'s' if len(result.rows) != 1 else ''} found")
    if result.rows:
        st.dataframe(result.rows, use_container_width=True, hide_index=True)
    else:
        st.info("The query ran cleanly but returned no matching rows.")

    with st.expander("Show the SQL that was run", expanded=False):
        st.code(result.executed_sql, language="sql")

    fb_col1, fb_col2, fb_spacer = st.columns([1, 1, 4])
    turn = st.session_state.turns[idx]
    with fb_col1:
        if st.button("👍 Yes", key=f"up_{idx}", use_container_width=True):
            turn["feedback"] = "up"
    with fb_col2:
        if st.button("👎 Not quite", key=f"down_{idx}", use_container_width=True):
            turn["feedback"] = "down"

    if turn["feedback"] == "up":
        st.caption("Glad that landed. Ask another question whenever you're ready.")
    elif turn["feedback"] == "down":
        st.caption("Got it -- type what you actually meant in the box below and I'll use this "
                   "question as context for the next try.")


# ------------------------------------------------------------------
# Header
# ------------------------------------------------------------------
st.markdown(f"""
<div class="ts-hero">
    <div class="ts-hero-title">🎬 TrendScout</div>
    <div class="ts-hero-sub">
        Ask what's trending in plain English -- typos and all. Every answer
        shows exactly what was understood and exactly what SQL ran, so
        nothing is a black box.
    </div>
    <div class="ts-badges">
        <span class="ts-badge">⚡ {DEFAULT_MODEL}</span>
        <span class="ts-badge">🔒 Read-only + guardrailed SQL</span>
        <span class="ts-badge">🗄️ SQLite</span>
    </div>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### What TrendScout can do")
    st.markdown(CAPABILITIES_BLURB)
    st.divider()
    if st.button("🗑️ Clear conversation", use_container_width=True):
        st.session_state.turns = []
        st.rerun()

# ------------------------------------------------------------------
# Example chips (only before the first question, to keep things uncluttered)
# ------------------------------------------------------------------
if not st.session_state.turns:
    st.markdown("**Try one of these:**")
    chip_cols = st.columns(2)
    for i, example in enumerate(EXAMPLES):
        with chip_cols[i % 2]:
            if st.button(example, key=f"chip_{i}", use_container_width=True):
                st.session_state.pending_question = example

# ------------------------------------------------------------------
# Render chat history
# ------------------------------------------------------------------
for i, turn in enumerate(st.session_state.turns):
    with st.chat_message("user"):
        st.markdown(turn["question"])
    with st.chat_message("assistant", avatar="🎬"):
        _render_result(i, turn["result"])

# ------------------------------------------------------------------
# Input (either from a clicked example chip or the chat box)
# ------------------------------------------------------------------
typed_question = st.chat_input("Ask about movie or show trends...")
incoming_question = st.session_state.pending_question or typed_question
st.session_state.pending_question = None

if incoming_question:
    _run_turn(incoming_question)
    st.rerun()
