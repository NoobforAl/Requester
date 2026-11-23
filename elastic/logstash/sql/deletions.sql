-- Deleted rows (analytics.DeletedRow, written by Django on every delete) become
-- deletes in their index. 5 minutes of overlap, as in the other queries: a
-- delete sent twice is harmless.
SELECT
    `index` AS target_index,
    row_id,
    deleted_at
FROM analytics_deletedrow
WHERE deleted_at > DATE_SUB(:sql_last_value, INTERVAL 5 MINUTE)
ORDER BY deleted_at
