"""Builds a data set that can grow, so query counts can be compared at two sizes.

The factories come from ``src/conftest.py`` (``make_employer`` and friends); they are
passed in because plain helpers cannot request pytest fixtures themselves.
"""

from dataclasses import dataclass, field

from applications.models import Application
from candidates.models import Candidate, JobAlert, SavedPosting
from employers.models import Employer, JobPosting, Skill, WorkMode


@dataclass
class Scenario:
    make_employer: object
    make_candidate: object
    make_posting: object
    make_application: object

    employer: Employer = field(init=False)
    candidate: Candidate = field(init=False)
    skills: list[Skill] = field(init=False)
    postings: list[JobPosting] = field(default_factory=list, init=False)
    applicants: list[Candidate] = field(default_factory=list, init=False)
    alerts: list[JobAlert] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.employer = self.make_employer("acme")
        self.skills = [Skill.objects.create(name=f"skill-{i}") for i in range(4)]
        self.candidate = self.make_candidate(
            "sara",
            headline="Backend developer",
            preferred_work_mode=WorkMode.REMOTE,
            expected_salary=50_000,
        )
        self.candidate.skills.set(self.skills[:2])

    def grow(self, n: int) -> "Scenario":
        """Add objects until there are ``n`` of each kind (postings, alerts...)."""
        for i in range(len(self.postings), n):
            posting = self.make_posting(
                self.employer,
                title=f"Job {i}",
                location="Berlin",
                salary_min=40_000,
                salary_max=60_000,
            )
            # Every posting has skills, so a missing prefetch shows up as N queries.
            posting.skills.set(self.skills[i % 3 : i % 3 + 2])
            self.postings.append(posting)

            # The candidate applies to and saves every posting.
            self.make_application(self.candidate, posting)
            SavedPosting.objects.create(candidate=self.candidate, posting=posting)

            # Other candidates apply to the first posting (the employer detail page).
            applicant = self.make_candidate(f"applicant{i}", headline="Developer")
            self.applicants.append(applicant)
            self.make_application(applicant, self.postings[0])

            alert = JobAlert.objects.create(
                candidate=self.candidate, name=f"Alert {i}", keywords="python"
            )
            alert.skills.set(self.skills[:2])
            self.alerts.append(alert)

        # Status history on the candidate's first application (candidate job detail).
        first = Application.objects.get(
            candidate=self.candidate, posting=self.postings[0]
        )
        for _ in range(first.events.count(), n):
            first.events.create(from_status="pending", to_status="in_review")
        return self
