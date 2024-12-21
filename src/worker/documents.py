from django_elasticsearch_dsl import Document, fields
from django_elasticsearch_dsl.registries import registry
from .models import JobRequest


@registry.register_document
class JobRequestsDocument(Document):
    worker = fields.ObjectField(properties={
        'first_name': fields.TextField(),
        'last_name': fields.TextField(),
        'email': fields.TextField(),
        'phone_number': fields.TextField(),
        'address': fields.TextField(),
        'date_of_birth': fields.DateField(),
    })
    job = fields.ObjectField(properties={
        'job_name': fields.TextField(),
        'detail': fields.TextField(),
        'offer': fields.ObjectField(properties={
            'company_name': fields.TextField(),
            'company_email': fields.TextField(),
        }),
    })

    class Index:
        name = 'job_requests'
        settings = {
            'number_of_shards': 1,
            'number_of_replicas': 0
        }

    class Django:
        model = JobRequest
        fields = [
            'resume',
            'cover_letter',
            'status',
            'applied_at',
            'updated_at',
        ]
