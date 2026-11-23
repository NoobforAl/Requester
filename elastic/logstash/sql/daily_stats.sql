-- requester-daily-stats: totals that only exist "right now" (how many jobs are
-- open today), one document per UTC day, overwritten every 15 minutes. History
-- builds up from the day the pipeline first runs. Counts per day of new postings,
-- applications or searches come from the other indices' dates instead.
SELECT
    CAST(UTC_DATE() AS CHAR) AS day_id,
    UTC_DATE() AS day,
    UTC_TIMESTAMP() AS measured_at,
    (SELECT COUNT(*) FROM employers_jobposting) AS postings,
    (SELECT COUNT(*) FROM employers_jobposting
      WHERE is_active AND (deadline IS NULL OR deadline >= UTC_DATE())) AS open_postings,
    (SELECT COUNT(DISTINCT employer_id) FROM employers_jobposting
      WHERE is_active AND (deadline IS NULL OR deadline >= UTC_DATE())) AS hiring_employers,
    (SELECT COUNT(*) FROM employers_employer) AS employers,
    (SELECT COUNT(*) FROM candidates_candidate) AS candidates,
    (SELECT COUNT(*) FROM candidates_candidate WHERE is_open_to_work) AS open_to_work_candidates,
    (SELECT COUNT(*) FROM applications_application
      WHERE status IN ('pending', 'in_review', 'shortlisted')) AS applications_in_progress
