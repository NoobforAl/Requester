-- requester-applications: one document per application (current status).
-- No candidate identity: no name, e-mail, resume, cover letter or notes; only
-- the candidate's city, experience and education, for "who applies" charts.
SELECT
    a.id,
    a.status,
    a.applied_at,
    a.updated_at AS changed_at,
    (a.ai_provider <> '') AS has_ai_summary,
    a.posting_id,
    p.title AS posting_title,
    p.work_mode,
    p.employment_type,
    NULLIF(p.seniority, '') AS seniority,
    NULLIF(p.location, '') AS posting_city,
    e.id AS employer_id,
    e.name AS employer_name,
    NULLIF(c.city, '') AS candidate_city,
    c.experience_years AS candidate_experience_years,
    NULLIF(c.education_level, '') AS candidate_education,
    (SELECT COUNT(*) FROM applications_applicationevent ev WHERE ev.application_id = a.id) AS status_changes
FROM applications_application a
JOIN employers_jobposting p ON p.id = a.posting_id
JOIN employers_employer e ON e.id = p.employer_id
JOIN candidates_candidate c ON c.id = a.candidate_id
WHERE a.updated_at > DATE_SUB(:sql_last_value, INTERVAL 5 MINUTE)
ORDER BY changed_at
