-- requester-postings: one document per job posting (current state), with its
-- company, skills and how many candidates applied and saved it.
-- Changed rows only (5 minutes of overlap: a slow transaction can commit a row
-- with an older timestamp than the last one seen); the nightly run passes the
-- epoch as :sql_last_value and so refreshes everything (counts, is_open).
SELECT
    p.id,
    p.title,
    p.description,
    NULLIF(p.location, '') AS location,
    NULLIF(p.country, '') AS country,
    p.work_mode,
    p.employment_type,
    NULLIF(p.seniority, '') AS seniority,
    p.salary_min,
    p.salary_max,
    p.salary_currency,
    p.deadline,
    p.is_active,
    (p.is_active AND (p.deadline IS NULL OR p.deadline >= UTC_DATE())) AS is_open,
    p.created_at,
    GREATEST(p.updated_at, e.updated_at) AS changed_at,
    e.id AS employer_id,
    e.name AS employer_name,
    NULLIF(e.industry, '') AS employer_industry,
    NULLIF(e.size, '') AS employer_size,
    NULLIF(e.city, '') AS employer_city,
    (SELECT GROUP_CONCAT(s.name ORDER BY s.name SEPARATOR '|')
       FROM employers_jobposting_skills ps
       JOIN employers_skill s ON s.id = ps.skill_id
      WHERE ps.jobposting_id = p.id) AS skills,
    (SELECT COUNT(*) FROM applications_application a WHERE a.posting_id = p.id) AS applications,
    (SELECT COUNT(*) FROM candidates_savedposting sp WHERE sp.posting_id = p.id) AS saves
FROM employers_jobposting p
JOIN employers_employer e ON e.id = p.employer_id
WHERE GREATEST(p.updated_at, e.updated_at) > DATE_SUB(:sql_last_value, INTERVAL 5 MINUTE)
ORDER BY changed_at
