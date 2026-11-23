-- requester-application-events: every status change of an application (rows are
-- never edited, so only new ones are read). For funnels and "time to answer".
SELECT
    ev.id,
    ev.application_id,
    a.posting_id,
    e.name AS employer_name,
    ev.from_status,
    ev.to_status,
    ev.created_at,
    ROUND(TIMESTAMPDIFF(SECOND, a.applied_at, ev.created_at) / 3600, 1) AS hours_since_applied,
    CASE
        WHEN ev.actor_id IS NULL THEN 'system'
        WHEN EXISTS (SELECT 1 FROM employers_employer x WHERE x.user_id = ev.actor_id) THEN 'employer'
        WHEN EXISTS (SELECT 1 FROM candidates_candidate x WHERE x.user_id = ev.actor_id) THEN 'candidate'
        ELSE 'staff'
    END AS actor
FROM applications_applicationevent ev
JOIN applications_application a ON a.id = ev.application_id
JOIN employers_jobposting p ON p.id = a.posting_id
JOIN employers_employer e ON e.id = p.employer_id
WHERE ev.created_at > DATE_SUB(:sql_last_value, INTERVAL 5 MINUTE)
ORDER BY ev.created_at
