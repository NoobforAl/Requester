from typing import Any

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Application


@receiver(post_delete, sender=Application)
def delete_resume_file(sender: type[Application], instance: Application, **kwargs: Any):
    """Remove the stored PDF once the row is really gone (also on cascades)."""
    resume = instance.resume
    name = resume.name
    if name:
        transaction.on_commit(lambda: resume.storage.delete(name))
