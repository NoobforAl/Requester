"""Builds a data set that can grow, so query counts can be compared at two sizes.

The objects come from ``tests/factories.py`` (Faker, fixed seed), so the text,
cities and salaries look real. The fields that change which queries a page runs
are fixed here: every posting is open, has exactly two skills, and every
application is pending, so N=2 and N=10 differ only in size.
"""

from dataclasses import dataclass, field

from applications.models import Application
from candidates.models import Candidate, JobAlert
from employers.models import Employer, JobPosting, Skill, WorkMode
from tests import factories

SEED = 1234


@dataclass
class Scenario:
    # Unused; kept so ``Scenario(make_employer, ...)`` with the conftest fixtures
    # still works. The data comes from ``tests.factories``.
    make_employer: object = None
    make_candidate: object = None
    make_posting: object = None
    make_application: object = None

    employer: Employer = field(init=False)
    candidate: Candidate = field(init=False)
    skills: list[Skill] = field(init=False)
    postings: list[JobPosting] = field(default_factory=list, init=False)
    applicants: list[Candidate] = field(default_factory=list, init=False)
    alerts: list[JobAlert] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        factories.seed(SEED)
        self.employer = factories.make_employer()
        self.skills = factories.make_skill_pool(["Python", "Django", "SQL", "Docker"])
        self.candidate = factories.make_candidate(
            headline="Backend developer",
            preferred_work_mode=WorkMode.REMOTE,
            expected_salary=50_000,
            skills=self.skills[:2],
        )

    def grow(self, n: int) -> "Scenario":
        """Add objects until there are ``n`` of each kind (postings, alerts...)."""
        for i in range(len(self.postings), n):
            # "Job <i>" keeps titles unique and matches the ``q=Job`` search.
            posting = factories.make_posting(
                self.employer,
                title=f"Job {i}: {factories.job_title()}"[:100],
                is_active=True,
                deadline=None,
                salary_min=40_000,
                salary_max=60_000,
                # Every posting has skills, so a missing prefetch shows up as N queries.
                skills=self.skills[i % 3 : i % 3 + 2],
            )
            self.postings.append(posting)

            # The candidate applies to and saves every posting.
            factories.make_application(
                self.candidate, posting, status="pending", events=False
            )
            factories.make_saved(self.candidate, posting)

            # Other candidates apply to the first posting (the employer detail page).
            applicant = factories.make_candidate(headline="Developer")
            self.applicants.append(applicant)
            factories.make_application(
                applicant, self.postings[0], status="pending", events=False
            )

            alert = factories.make_alert(
                self.candidate,
                name=f"Alert {i}",
                keywords="python",
                skills=self.skills[:2],
            )
            self.alerts.append(alert)

        # Status history on the candidate's first application (candidate job detail).
        first = Application.objects.get(
            candidate=self.candidate, posting=self.postings[0]
        )
        for _ in range(first.events.count(), n):
            first.events.create(from_status="pending", to_status="in_review")
        return self
