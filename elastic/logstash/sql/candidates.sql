-- requester-candidates: the supply side, without identity (no name, e-mail,
-- phone, birth date, address, links or salary): city, experience, education,
-- preferred work mode and skills. The document id is the row id, not stored.
SELECT
    c.id,
    NULLIF(c.city, '') AS city,
    c.experience_years,
    NULLIF(c.education_level, '') AS education_level,
    NULLIF(c.preferred_work_mode, '') AS preferred_work_mode,
    c.is_open_to_work,
    c.language,
    c.created_at,
    c.updated_at AS changed_at,
    (SELECT GROUP_CONCAT(s.name ORDER BY s.name SEPARATOR '|')
       FROM candidates_candidate_skills cs
       JOIN employers_skill s ON s.id = cs.skill_id
      WHERE cs.candidate_id = c.id) AS skills
FROM candidates_candidate c
WHERE c.updated_at > DATE_SUB(:sql_last_value, INTERVAL 5 MINUTE)
ORDER BY changed_at
