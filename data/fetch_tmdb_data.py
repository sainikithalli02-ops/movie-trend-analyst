"""
Pulls real movie data from The Movie Database (TMDB) API and writes it in
the same shape as generate_seed_data.py, so it can be loaded by init_db.py.

Get a free API key: https://www.themoviedb.org/settings/api
Then set it as an environment variable:
    export TMDB_API_KEY="your_key_here"

Run monthly (e.g. via a GitHub Actions cron job) to build up real
rating_snapshots history over time -- that history is what makes the
"trending" and "momentum" SQL queries meaningful. Until you've collected
a few months of real snapshots, use the synthetic seed data to develop
and demo against.

Usage:
    python data/fetch_tmdb_data.py --pages 5
"""

import argparse
import os
import sys
import time
from datetime import date

try:
    import requests
except ImportError:
    sys.exit("Install requests first: pip install requests")

TMDB_BASE = "https://api.themoviedb.org/3"
GENRE_MAP_CACHE = {}


def _get(session, path, api_key, params=None):
    params = dict(params or {})
    params["api_key"] = api_key
    resp = session.get(f"{TMDB_BASE}{path}", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_genre_map(session, api_key):
    global GENRE_MAP_CACHE
    if GENRE_MAP_CACHE:
        return GENRE_MAP_CACHE
    data = _get(session, "/genre/movie/list", api_key)
    GENRE_MAP_CACHE = {g["id"]: g["name"] for g in data["genres"]}
    return GENRE_MAP_CACHE


def fetch_popular_movies(session, api_key, pages: int):
    """Pulls `pages` pages (20 movies each) of currently popular movies."""
    movies = []
    for page in range(1, pages + 1):
        data = _get(session, "/movie/popular", api_key, {"page": page})
        movies.extend(data.get("results", []))
        time.sleep(0.25)  # be polite to the free-tier rate limit
    return movies


def to_rows(movies, genre_map):
    """Reshapes TMDB's JSON into rows matching schema.sql's tables."""
    movie_rows, genre_link_rows, snapshot_rows = [], [], []
    today = date.today().replace(day=1).isoformat()

    for m in movies:
        movie_id = m["id"]
        movie_rows.append({
            "movie_id": movie_id,
            "title": m.get("title"),
            "release_year": int((m.get("release_date") or "0000")[:4] or 0) or None,
            "runtime_minutes": None,  # requires a /movie/{id} detail call; add if needed
            "original_language": m.get("original_language"),
            "director": None,         # requires a /movie/{id}/credits call; add if needed
            "budget_usd": None,
            "revenue_usd": None,
            "overview": m.get("overview"),
            "reviewed_by_channel": 0,
        })
        for genre_id in m.get("genre_ids", []):
            genre_link_rows.append((movie_id, genre_map.get(genre_id, "Unknown")))
        snapshot_rows.append((
            movie_id, today, m.get("vote_average", 0), m.get("vote_count", 0)
        ))

    return movie_rows, genre_link_rows, snapshot_rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages", type=int, default=5, help="TMDB pages to pull (20 movies/page)")
    args = parser.parse_args()

    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        sys.exit("Set TMDB_API_KEY in your environment first. See docstring for how to get one.")

    session = requests.Session()
    genre_map = fetch_genre_map(session, api_key)
    movies = fetch_popular_movies(session, api_key, args.pages)
    movie_rows, genre_link_rows, snapshot_rows = to_rows(movies, genre_map)

    print(f"Fetched {len(movie_rows)} movies, "
          f"{len(genre_link_rows)} genre links, "
          f"{len(snapshot_rows)} rating snapshots.")
    print("Wire these into init_db.py's insert step to load real data "
          "instead of the synthetic seed set.")


if __name__ == "__main__":
    main()
