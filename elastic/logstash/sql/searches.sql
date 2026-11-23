-- requester-searches: every search on the candidate job list (candidates.JobSearch;
-- rows are never edited, so only new ones are read). No user is stored.
SELECT
    js.id,
    NULLIF(js.query, '') AS query,
    NULLIF(js.location, '') AS location,
    NULLIF(js.work_mode, '') AS work_mode,
    NULLIF(js.employment_type, '') AS employment_type,
    NULLIF(js.seniority, '') AS seniority,
    js.min_salary,
    js.remote_only,
    NULLIF(js.language, '') AS language,
    js.results,
    (js.results = 0) AS zero_results,
    js.created_at,
    (SELECT GROUP_CONCAT(s.name ORDER BY s.name SEPARATOR '|')
       FROM candidates_jobsearch_skills jss
       JOIN employers_skill s ON s.id = jss.skill_id
      WHERE jss.jobsearch_id = js.id) AS skills
FROM candidates_jobsearch js
WHERE js.created_at > DATE_SUB(:sql_last_value, INTERVAL 5 MINUTE)
ORDER BY js.created_at
