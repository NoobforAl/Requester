from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from offer.models import Offer


class Command(BaseCommand):
    help = 'Insert multiple offers into the database,'
    ' creating users if they do not exist'

    def handle(self, *args, **kwargs):
        # Sample data for offers
        offers_to_insert = [
            {
                'username': 'alice',
                'company_name': 'Google',
                'company_email': 'alice@google.com',
                'detail': 'Developing innovative solutions at Google.',
                'password': 'password123',
            },
            {
                'username': 'bob',
                'company_name': 'Google',
                'company_email': 'bob@google.com',
                'detail': 'Leading projects in cloud computing.',
                'password': 'password123',
            },
            {
                'username': 'charlie',
                'company_name': 'Google',
                'company_email': 'charlie@google.com',
                'detail': 'Enhancing user experience in Google Search.',
                'password': 'password123',
            },
            {
                'username': 'dave',
                'company_name': 'Google',
                'company_email': 'dave@google.com',
                'detail': 'Working on artificial'
                ' intelligence and machine learning.',
                'password': 'password123',
            },
            {
                'username': 'eve',
                'company_name': 'Google',
                'company_email': 'eve@google.com',
                'detail': 'Focusing on cybersecurity measures.',
                'password': 'password123',
            },
            {
                'username': 'frank',
                'company_name': 'Microsoft',
                'company_email': 'frank@microsoft.com',
                'detail': 'Innovating solutions for enterprise software.',
                'password': 'password123',
            },
            {
                'username': 'grace',
                'company_name': 'Amazon',
                'company_email': 'grace@amazon.com',
                'detail': 'Optimizing logistics for better delivery systems.',
                'password': 'password123',
            },
            {
                'username': 'heidi',
                'company_name': 'Apple',
                'company_email': 'heidi@apple.com',
                'detail': 'Designing intuitive user interfaces for iOS apps.',
                'password': 'password123',
            },
            {
                'username': 'ivan',
                'company_name': 'Facebook',
                'company_email': 'ivan@facebook.com',
                'detail': 'Building social media engagement tools.',
                'password': 'password123',
            },
            {
                'username': 'judy',
                'company_name': 'Netflix',
                'company_email': 'judy@netflix.com',
                'detail': 'Creating recommendations systems'
                ' for movies and shows.',
                'password': 'password123',
            },
        ]

        for offer_data in offers_to_insert:
            user, created = User.objects.get_or_create(
                username=offer_data['username'],
                defaults={
                    'email': offer_data['company_email'],
                    'password': offer_data['password'],
                }
            )
            if created:
                user.set_password(offer_data['password'])
                user.save()
                self.stdout.write(self.style.SUCCESS(
                    f'Successfully created user: {offer_data["username"]}'))
            else:
                self.stdout.write(self.style.WARNING(
                    f'User already exists: {offer_data["username"]}'))

            offer, created = Offer.objects.get_or_create(
                user=user,
                company_name=offer_data['company_name'],
                company_email=offer_data['company_email'],
                detail=offer_data['detail']
            )
            if created:
                self.stdout.write(self.style.SUCCESS(
                    f'Successfully added offer for: {offer_data["username"]}'))
            else:
                self.stdout.write(self.style.WARNING(
                    f'Offer already exists for: {offer_data["username"]}'))
