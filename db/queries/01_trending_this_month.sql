-- Which titles are gaining the most ratings/votes momentum this month?
-- This is the core "what should I review next" query.
-- Demonstrates: window functions (LAG), CTEs, derived metrics.

WITH ranked_snapshots AS (
    SELECT
        movie_id,
        snapshot_date,
        rating,
        votes,
        LAG(rating) OVER (PARTITION BY movie_id ORDER BY snapshot_date) AS prev_rating,
        LAG(votes)  OVER (PARTITION BY movie_id ORDER BY snapshot_date) AS prev_votes,
        ROW_NUMBER() OVER (PARTITION BY movie_id ORDER BY snapshot_date DESC) AS recency_rank
    FROM rating_snapshots
),
latest AS (
    SELECT
        movie_id,
        rating,
        votes,
        prev_rating,
        prev_votes,
        ROUND(rating - prev_rating, 2)              AS rating_delta,
        ROUND(1.0 * (votes - prev_votes) / NULLIF(prev_votes, 0) * 100, 1) AS vote_growth_pct
    FROM ranked_snapshots
    WHERE recency_rank = 1
      AND prev_rating IS NOT NULL
)
SELECT
    m.title,
    m.release_year,
    GROUP_CONCAT(DISTINCT g.genre_name) AS genres,
    l.rating,
    l.rating_delta,
    l.vote_growth_pct,
    m.reviewed_by_channel
FROM latest l
JOIN movies m        ON m.movie_id = l.movie_id
JOIN movie_genres mg ON mg.movie_id = m.movie_id
JOIN genres g         ON g.genre_id = mg.genre_id
WHERE m.reviewed_by_channel = 0            -- only surface titles not yet covered
GROUP BY m.movie_id
ORDER BY l.rating_delta DESC, l.vote_growth_pct DESC
LIMIT 15;
