"""
Generates a realistic, relational seed dataset so the project can be run
and demoed immediately after cloning -- no API key required.

For the *real* version of this project, run data/fetch_tmdb_data.py instead
(needs a free TMDB API key). This seed generator exists purely so a
recruiter or interviewer can `python init_db.py` and get a working demo
in under a minute.

Run directly to preview the data it would create:
    python data/generate_seed_data.py
"""

import random
from datetime import date, timedelta

random.seed(42)

GENRES = [
    "Action", "Drama", "Comedy", "Thriller", "Horror", "Sci-Fi",
    "Romance", "Animation", "Documentary", "Crime", "Fantasy", "Mystery",
]

PLATFORMS = ["Netflix", "Prime Video", "Disney+ Hotstar", "JioCinema", "Apple TV+", "Theatrical"]

DIRECTORS = [
    "A. Rao", "S. Menon", "K. Iyer", "P. Fernandes", "R. Kapoor",
    "L. Chen", "M. Alvarez", "J. Okafor", "T. Nakamura", "D. Silva",
]

TITLE_WORDS_A = ["Shadow", "Crimson", "Silent", "Last", "Broken", "Golden",
                 "Midnight", "Hollow", "Eternal", "Forgotten", "Rogue", "Iron"]
TITLE_WORDS_B = ["Signal", "Harbor", "Kingdom", "Protocol", "Echo", "Horizon",
                 "Verdict", "Circuit", "Legacy", "Mirage", "Descent", "Uprising"]


def make_title(i: int) -> str:
    return f"{random.choice(TITLE_WORDS_A)} {random.choice(TITLE_WORDS_B)}"


def generate_movies(n_movies: int = 220):
    movies = []
    for movie_id in range(1, n_movies + 1):
        release_year = random.choice(range(2018, 2027))
        runtime = random.randint(85, 175)
        budget = random.choice([0, 2_000_000, 8_000_000, 25_000_000, 60_000_000, 120_000_000])
        revenue_multiplier = random.uniform(0.4, 4.0)
        revenue = int(budget * revenue_multiplier) if budget else random.randint(0, 5_000_000)
        movies.append({
            "movie_id": movie_id,
            "title": f"{make_title(movie_id)} ({release_year})",
            "release_year": release_year,
            "runtime_minutes": runtime,
            "original_language": random.choice(["en", "hi", "te", "ta", "ko", "ja"]),
            "director": random.choice(DIRECTORS),
            "budget_usd": budget,
            "revenue_usd": revenue,
            "overview": "Synthetic placeholder overview -- replace with real TMDB data.",
            "reviewed_by_channel": 1 if random.random() < 0.15 else 0,
        })
    return movies


def generate_movie_genres(movies):
    rows = []
    for m in movies:
        genre_ids = random.sample(range(1, len(GENRES) + 1), k=random.randint(1, 3))
        for g in genre_ids:
            rows.append((m["movie_id"], g))
    return rows


def generate_movie_platforms(movies):
    rows = []
    for m in movies:
        platform_ids = random.sample(range(1, len(PLATFORMS) + 1), k=random.randint(1, 2))
        base_date = date(m["release_year"], random.randint(1, 12), random.randint(1, 28))
        for p in platform_ids:
            rows.append((m["movie_id"], p, base_date.isoformat()))
    return rows


def generate_rating_snapshots(movies, n_months: int = 6):
    """
    Builds a monthly rating/vote-count history per movie so the SQL layer
    can compute real momentum (this month's rating minus last month's,
    rolling averages, etc.) instead of working off a single static number.
    Roughly a third of movies get a clear upward trend in the most recent
    months -- these are the ones the "trending" queries should surface.
    """
    rows = []
    today = date.today().replace(day=1)
    months = [today - timedelta(days=30 * i) for i in range(n_months)][::-1]

    for m in movies:
        base_rating = round(random.uniform(4.5, 8.5), 1)
        base_votes = random.randint(500, 50_000)
        is_trending_up = random.random() < 0.3
        rating = base_rating
        votes = base_votes
        for month_date in months:
            if is_trending_up:
                rating = min(9.8, rating + random.uniform(0.05, 0.35))
                votes = int(votes * random.uniform(1.15, 1.6))
            else:
                rating = max(1.0, rating + random.uniform(-0.15, 0.15))
                votes = int(votes * random.uniform(0.95, 1.1))
            rows.append((m["movie_id"], month_date.isoformat(), round(rating, 2), votes))
    return rows


if __name__ == "__main__":
    movies = generate_movies(10)
    print(f"Sample movie row: {movies[0]}")
    print(f"Genre links: {generate_movie_genres(movies)[:5]}")
    print(f"Snapshot rows for movie 1: "
          f"{[r for r in generate_rating_snapshots(movies) if r[0] == 1]}")
