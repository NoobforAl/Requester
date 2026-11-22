from django_elasticsearch_dsl import Document, fields
from django_elasticsearch_dsl.registries import registry

from .models import JobPosting


@registry.register_document
class JobPostingsDocument(Document):
    skills = fields.ObjectField(
        properties={
            "name": fields.TextField(),
        }
    )
    employer = fields.ObjectField(
        properties={
            "name": fields.TextField(),
        }
    )

    class Index:
        name = "job_postings"
        settings = {
            "number_of_shards": 1,
            "number_of_replicas": 0,
        }

    class Django:
        model = JobPosting

        fields = [
            "title",
            "description",
            "location",
            "country",
            "work_mode",
            "employment_type",
            "seniority",
            "salary_min",
            "salary_max",
            "salary_currency",
            "deadline",
            "is_active",
        ]
        related_models = ["employers.Employer", "employers.Skill"]

    def get_instances_from_related(self, related_instance):
        if hasattr(related_instance, "postings"):
            return related_instance.postings.all()
        return None
