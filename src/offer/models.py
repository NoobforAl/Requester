from django.contrib.auth.models import User
from django.db import models
from django.db.models.functions import Lower


class Offer(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name="User")
    company_name = models.CharField(max_length=30, verbose_name="Company Name")
    company_email = models.EmailField(unique=True, verbose_name="Company Email")
    detail = models.TextField(blank=True, default="", verbose_name="Detail")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Offer"
        verbose_name_plural = "Offers"
        ordering = ("company_name",)
        constraints = (
            models.UniqueConstraint(
                Lower("company_email"), name="unique_offer_company_email_ci"
            ),
        )

    def __str__(self):
        return f"{self.user.username} ({self.company_name})"


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name="Tag Name")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tag"
        verbose_name_plural = "Tags"
        ordering = ("name",)

    def __str__(self):
        return self.name


class Job(models.Model):
    job_name = models.CharField(max_length=100, verbose_name="Job Name")
    detail = models.TextField(verbose_name="Detail")
    tags = models.ManyToManyField(Tag, blank=True, verbose_name="Tags")
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, verbose_name="Offer")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Job"
        verbose_name_plural = "Jobs"
        ordering = ("-created_at", "-id")
        indexes = (
            models.Index(fields=["offer", "-created_at"], name="job_offer_created_idx"),
        )
        constraints = (
            models.UniqueConstraint(
                fields=["job_name", "offer"], name="unique_job_offer"
            ),
        )

    def __str__(self):
        return f"{self.job_name} at {self.offer.company_name}"
