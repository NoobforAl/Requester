"""Container-aware pool sizing and the fast form renderer."""

import re

import pytest
from django.forms.renderers import DjangoTemplates

from candidates.form import JobAlertForm, JobFilterForm, ProfileForm
from employers.form import JobPostingForm
from employers.models import Skill
from requester import runtime


@pytest.fixture
def host_cpus(monkeypatch):
    def _set(count: int) -> None:
        monkeypatch.setattr(
            runtime.os,
            "sched_getaffinity",
            lambda _pid: set(range(count)),
            raising=False,
        )

    return _set


@pytest.mark.parametrize(
    ("quota", "expected"),
    [(None, 8), (2.0, 2), (0.5, 1), (1.5, 2), (16.0, 8)],
)
def test_cpu_count_follows_the_container_limit(monkeypatch, host_cpus, quota, expected):
    host_cpus(8)
    monkeypatch.setattr(runtime, "_cgroup_cpu_quota", lambda: quota)
    assert runtime.container_cpu_count() == expected


def test_cgroup_v2_quota_is_read(monkeypatch, tmp_path):
    cpu_max = tmp_path / "cpu.max"
    cpu_max.write_text("150000 100000\n")
    real_path = runtime.Path
    monkeypatch.setattr(
        runtime,
        "Path",
        lambda p: (
            cpu_max if p == "/sys/fs/cgroup/cpu.max" else real_path(tmp_path / "x")
        ),
    )
    assert runtime._cgroup_cpu_quota() == 1.5

    cpu_max.write_text("max 100000\n")
    assert runtime._cgroup_cpu_quota() is None


def _normalise(html: str) -> str:
    return re.sub(r">\s+<", "><", re.sub(r"\s+", " ", html)).strip()


@pytest.mark.django_db
@pytest.mark.parametrize("form_class", [JobFilterForm, JobPostingForm, JobAlertForm])
def test_fast_renderer_gives_the_same_markup(form_class):
    Skill.objects.bulk_create(Skill(name=f"skill {i}") for i in range(5))

    def html(**kwargs) -> str:
        return _normalise("".join(str(field) for field in form_class(**kwargs)))

    fast = html()
    assert "skill 4" in fast
    assert fast == html(renderer=DjangoTemplates())


def test_fast_renderer_is_used_by_the_skills_forms():
    for form_class in (JobFilterForm, JobPostingForm, JobAlertForm, ProfileForm):
        assert type(form_class().renderer).__name__ == "Jinja2"
