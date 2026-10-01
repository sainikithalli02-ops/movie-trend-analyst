"""
Creates trendscout.db, applies db/schema.sql, and loads the synthetic
seed dataset (data/generate_seed_data.py) so the project is immediately
runnable end to end.

Usage:
    python init_db.py
"""

import sqlite3
from pathlib import Path

from data.generate_seed_data import (
    GENRES, PLATFORMS,
    generate_movies, generate_movie_genres,
    generate_movie_platforms, generate_rating_snapshots,
)

DB_PATH = Path(__file__).parent / "trendscout.db"
SCHEMA_PATH = Path(__file__).parent / "db" / "schema.sql"


def build_database():
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_PATH.read_text())

    conn.executemany(
        "INSERT INTO genres (genre_id, genre_name) VALUES (?, ?)",
        list(enumerate(GENRES, start=1)),
    )
    conn.executemany(
        "INSERT INTO platforms (platform_id, platform_name) VALUES (?, ?)",
        list(enumerate(PLATFORMS, start=1)),
    )

    movies = generate_movies()
    conn.executemany(
        """INSERT INTO movies
           (movie_id, title, release_year, runtime_minutes, original_language,
            director, budget_usd, revenue_usd, overview, reviewed_by_channel)
           VALUES (:movie_id, :title, :release_year, :runtime_minutes,
                   :original_language, :director, :budget_usd, :revenue_usd,
                   :overview, :reviewed_by_channel)""",
        movies,
    )

    conn.executemany(
        "INSERT INTO movie_genres (movie_id, genre_id) VALUES (?, ?)",
        generate_movie_genres(movies),
    )
    conn.executemany(
        "INSERT INTO movie_platforms (movie_id, platform_id, added_date) VALUES (?, ?, ?)",
        generate_movie_platforms(movies),
    )
    conn.executemany(
        "INSERT INTO rating_snapshots (movie_id, snapshot_date, rating, votes) VALUES (?, ?, ?, ?)",
        generate_rating_snapshots(movies),
    )

    conn.commit()

    counts = {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ["movies", "genres", "platforms", "movie_genres",
                       "movie_platforms", "rating_snapshots"]
    }
    conn.close()
    return counts


if __name__ == "__main__":
    counts = build_database()
    print(f"Built {DB_PATH.name} with:")
    for table, n in counts.items():
        print(f"  {table:<18} {n} rows")
    print("\nTry it: sqlite3 trendscout.db < db/queries/01_trending_this_month.sql")
