-- Which genres are gaining average rating month over month?
-- Demonstrates: multi-table joins, aggregation, self-referencing
-- month-on-month comparison via window functions.

WITH genre_monthly AS (
    SELECT
        g.genre_name,
        rs.snapshot_date,
        ROUND(AVG(rs.rating), 2)  AS avg_rating,
        SUM(rs.votes)             AS total_votes
    FROM rating_snapshots rs
    JOIN movie_genres mg ON mg.movie_id = rs.movie_id
    JOIN genres g         ON g.genre_id = mg.genre_id
    GROUP BY g.genre_name, rs.snapshot_date
),
with_growth AS (
    SELECT
        genre_name,
        snapshot_date,
        avg_rating,
        total_votes,
        avg_rating - LAG(avg_rating) OVER (
            PARTITION BY genre_name ORDER BY snapshot_date
        ) AS mom_rating_change
    FROM genre_monthly
)
SELECT *
FROM with_growth
WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM rating_snapshots)
ORDER BY mom_rating_change DESC;
