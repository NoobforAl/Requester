"""Keep ``JobPosting.updated_at`` moving when what a job card shows changes.

The cached job cards (``candidates.job_cache``) are keyed by ``updated_at``. A
posting's own edits move it already; these signals cover the skills: adding or
removing a skill, and renaming or deleting a skill used by postings.
"""

from django.db.models.signals import m2m_changed, post_save, pre_delete
from django.dispatch import receiver
from django.utils import timezone

from .models import JobPosting, Skill


def touch(postings) -> None:
    postings.update(updated_at=timezone.now())


@receiver(m2m_changed, sender=JobPosting.skills.through)
def posting_skills_changed(sender, instance, action, reverse, pk_set, **kwargs):
    if action not in {"post_add", "post_remove", "post_clear", "pre_clear"}:
        return
    if not reverse:  # posting.skills.add(...): instance is the posting
        touch(JobPosting.objects.filter(pk=instance.pk))
    elif action == "pre_clear":  # skill.postings.clear(): find them before
        touch(JobPosting.objects.filter(skills=instance))
    elif pk_set:  # skill.postings.add/remove(...)
        touch(JobPosting.objects.filter(pk__in=pk_set))


@receiver(post_save, sender=Skill)
def skill_saved(sender, instance, created, raw=False, **kwargs):
    if not created and not raw:  # a rename shows on every card that has it
        touch(JobPosting.objects.filter(skills=instance))


@receiver(pre_delete, sender=Skill)
def skill_deleted(sender, instance, **kwargs):
    touch(JobPosting.objects.filter(skills=instance))
