"""A simple, explainable "how well does this posting fit me" score (0-100).

* skills (60 points): the share of the posting's skills the candidate has. A posting
  that lists no skills gets a neutral 30.
* work mode (20 points): full when it equals the candidate's preference, neutral 10
  when the candidate has no preference.
* salary (20 points): full when the posting's top salary reaches the candidate's
  expectation in the same currency, neutral 10 when either side is unknown.

Postings must have ``skills`` prefetched (``prefetch_related("skills")``) so ranking a
page of postings does not run one query per posting.
"""

from employers.models import JobPosting

from .models import Candidate

SKILLS_POINTS = 60
WORK_MODE_POINTS = 20
SALARY_POINTS = 20


def candidate_skill_ids(candidate: Candidate) -> set[int]:
    return set(candidate.skills.values_list("pk", flat=True))


def match_score(
    candidate: Candidate, posting: JobPosting, skill_ids: set[int] | None = None
) -> int:
    """Score ``posting`` for ``candidate``; pass ``skill_ids`` to reuse one lookup."""
    if skill_ids is None:
        skill_ids = candidate_skill_ids(candidate)

    wanted = {skill.pk for skill in posting.skills.all()}
    skills = SKILLS_POINTS * len(wanted & skill_ids) / len(wanted) if wanted else 30

    work_mode: float
    if not candidate.preferred_work_mode:
        work_mode = WORK_MODE_POINTS / 2
    else:
        work_mode = (
            WORK_MODE_POINTS
            if candidate.preferred_work_mode == posting.work_mode
            else 0
        )

    top = posting.salary_max or posting.salary_min
    salary: float
    if (
        candidate.expected_salary
        and top
        and candidate.expected_salary_currency == posting.salary_currency
    ):
        salary = SALARY_POINTS if candidate.expected_salary <= top else 0
    else:
        salary = SALARY_POINTS / 2

    return round(skills + work_mode + salary)
