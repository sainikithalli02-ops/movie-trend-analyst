-- Which titles have grown in rating for 3+ consecutive months in a row?
-- (Not just "up overall" -- genuinely trending, month after month.)
-- Demonstrates: the classic "consecutive pattern" SQL problem -- flag each
-- month as up/down, group consecutive "up" runs using the
-- row_number-minus-row_number gaps-and-islands trick, then filter by streak length.

WITH deltas AS (
    SELECT
        movie_id,
        snapshot_date,
        rating,
        rating - LAG(rating) OVER (PARTITION BY movie_id ORDER BY snapshot_date) AS delta
    FROM rating_snapshots
),
flagged AS (
    SELECT
        movie_id,
        snapshot_date,
        rating,
        CASE WHEN delta > 0 THEN 1 ELSE 0 END AS is_up
    FROM deltas
    WHERE delta IS NOT NULL
),
islands AS (
    SELECT
        movie_id,
        snapshot_date,
        rating,
        is_up,
        ROW_NUMBER() OVER (PARTITION BY movie_id ORDER BY snapshot_date)
            - ROW_NUMBER() OVER (PARTITION BY movie_id, is_up ORDER BY snapshot_date) AS island_id
    FROM flagged
),
streaks AS (
    SELECT
        movie_id,
        island_id,
        is_up,
        COUNT(*) AS streak_length,
        MAX(snapshot_date) AS streak_end_date
    FROM islands
    WHERE is_up = 1
    GROUP BY movie_id, island_id, is_up
    HAVING COUNT(*) >= 3
)
SELECT
    m.title,
    s.streak_length AS consecutive_months_up,
    s.streak_end_date
FROM streaks s
JOIN movies m ON m.movie_id = s.movie_id
ORDER BY s.streak_length DESC;
