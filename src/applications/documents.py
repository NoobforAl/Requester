from django_elasticsearch_dsl import Document, fields
from django_elasticsearch_dsl.registries import registry

from .models import Application


@registry.register_document
class ApplicationsDocument(Document):
    candidate = fields.ObjectField(
        properties={
            "first_name": fields.TextField(),
            "last_name": fields.TextField(),
            "email": fields.TextField(),
            "headline": fields.TextField(),
            "city": fields.TextField(),
            "experience_years": fields.IntegerField(),
        }
    )
    posting = fields.ObjectField(
        properties={
            "title": fields.TextField(),
            "description": fields.TextField(),
            "employer": fields.ObjectField(
                properties={
                    "name": fields.TextField(),
                    "contact_email": fields.TextField(),
                }
            ),
        }
    )

    class Index:
        name = "applications"
        settings = {"number_of_shards": 1, "number_of_replicas": 0}

    class Django:
        model = Application
        fields = [
            "cover_letter",
            "status",
            "applied_at",
            "updated_at",
        ]
