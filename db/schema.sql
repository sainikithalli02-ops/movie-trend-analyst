-- ============================================================
-- Schema: TrendScout movie/TV analytics database
-- A deliberately relational design (not one flat CSV table) so the
-- project demonstrates joins, normalization, and window-function-
-- friendly time series data -- not just SELECT * queries.
-- ============================================================

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS genres (
    genre_id    INTEGER PRIMARY KEY,
    genre_name  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS platforms (
    platform_id     INTEGER PRIMARY KEY,
    platform_name   TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS movies (
    movie_id            INTEGER PRIMARY KEY,
    title               TEXT NOT NULL,
    release_year        INTEGER,
    runtime_minutes     INTEGER,
    original_language   TEXT,
    director            TEXT,
    budget_usd          INTEGER,
    revenue_usd         INTEGER,
    overview            TEXT,
    reviewed_by_channel  INTEGER NOT NULL DEFAULT 0  -- 1 if Nikith has already covered it
);

CREATE TABLE IF NOT EXISTS movie_genres (
    movie_id    INTEGER NOT NULL REFERENCES movies(movie_id),
    genre_id    INTEGER NOT NULL REFERENCES genres(genre_id),
    PRIMARY KEY (movie_id, genre_id)
);

CREATE TABLE IF NOT EXISTS movie_platforms (
    movie_id        INTEGER NOT NULL REFERENCES movies(movie_id),
    platform_id     INTEGER NOT NULL REFERENCES platforms(platform_id),
    added_date      DATE NOT NULL,
    PRIMARY KEY (movie_id, platform_id)
);

-- Monthly rating/popularity snapshots. This is what makes "trending" and
-- "momentum" queries possible -- most tutorial movie datasets are a single
-- static snapshot, which is exactly what makes this project stand out.
CREATE TABLE IF NOT EXISTS rating_snapshots (
    snapshot_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    movie_id        INTEGER NOT NULL REFERENCES movies(movie_id),
    snapshot_date   DATE NOT NULL,   -- first of each month
    rating          REAL NOT NULL,   -- 0-10
    votes           INTEGER NOT NULL,
    UNIQUE(movie_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_movie_date ON rating_snapshots(movie_id, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_movies_year ON movies(release_year);
