-- High-vote, high-rating titles that haven't been reviewed yet AND aren't
-- available on a platform the channel usually covers -- i.e. content gaps.
-- Demonstrates: anti-join pattern (NOT EXISTS), multi-condition filtering.

SELECT
    m.title,
    m.release_year,
    latest.rating,
    latest.votes
FROM movies m
JOIN (
    SELECT movie_id, rating, votes
    FROM rating_snapshots rs
    WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM rating_snapshots)
) latest ON latest.movie_id = m.movie_id
WHERE m.reviewed_by_channel = 0
  AND latest.rating >= 7.0
  AND latest.votes  >= 5000
  AND NOT EXISTS (
      SELECT 1
      FROM movie_platforms mp
      JOIN platforms p ON p.platform_id = mp.platform_id
      WHERE mp.movie_id = m.movie_id
        AND p.platform_name IN ('Netflix', 'Prime Video')
  )
ORDER BY latest.rating DESC
LIMIT 15;
