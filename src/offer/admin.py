from django.contrib import admin

from offer.models import Job, Offer, Tag

admin.site.register(Offer)
admin.site.register(Job)
admin.site.register(Tag)
