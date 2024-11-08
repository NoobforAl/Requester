from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from worker.models import Worker


class Command(BaseCommand):
    help = 'Insert multiple workers into the database" \
    ", creating users if they do not exist'

    def handle(self, *args, **kwargs):
        # Sample data for workers
        workers_to_insert = [
            {
                'username': 'worker1',
                'first_name': 'John',
                'last_name': 'Doe',
                'email': 'john.doe@example.com',
                'phone_number': '1234567890',
                'address': '123 Main St, Anytown, USA',
                'date_of_birth': '1990-01-01',
                'password': 'password123',
            },
            {
                'username': 'worker2',
                'first_name': 'Jane',
                'last_name': 'Smith',
                'email': 'jane.smith@example.com',
                'phone_number': '0987654321',
                'address': '456 Elm St, Othertown, USA',
                'date_of_birth': '1992-02-02',
                'password': 'password123',
            },
            {
                'username': 'worker3',
                'first_name': 'Alice',
                'last_name': 'Johnson',
                'email': 'alice.johnson@example.com',
                'phone_number': '1112223333',
                'address': '789 Maple St, Anytown, USA',
                'date_of_birth': '1993-03-03',
                'password': 'password123',
            },
            {
                'username': 'worker4',
                'first_name': 'Bob',
                'last_name': 'Brown',
                'email': 'bob.brown@example.com',
                'phone_number': '4445556666',
                'address': '101 Pine St, Othertown, USA',
                'date_of_birth': '1994-04-04',
                'password': 'password123',
            },
            {
                'username': 'worker5',
                'first_name': 'Charlie',
                'last_name': 'Davis',
                'email': 'charlie.davis@example.com',
                'phone_number': '7778889999',
                'address': '202 Oak St, Anytown, USA',
                'date_of_birth': '1995-05-05',
                'password': 'password123',
            },
            {
                'username': 'worker6',
                'first_name': 'Diana',
                'last_name': 'Evans',
                'email': 'diana.evans@example.com',
                'phone_number': '0001112222',
                'address': '303 Birch St, Othertown, USA',
                'date_of_birth': '1996-06-06',
                'password': 'password123',
            },
            {
                'username': 'worker7',
                'first_name': 'Eve',
                'last_name': 'Foster',
                'email': 'eve.foster@example.com',
                'phone_number': '3334445555',
                'address': '404 Cedar St, Anytown, USA',
                'date_of_birth': '1997-07-07',
                'password': 'password123',
            },
            {
                'username': 'worker8',
                'first_name': 'Frank',
                'last_name': 'Green',
                'email': 'frank.green@example.com',
                'phone_number': '6667778888',
                'address': '505 Spruce St, Othertown, USA',
                'date_of_birth': '1998-08-08',
                'password': 'password123',
            },
            {
                'username': 'worker9',
                'first_name': 'Grace',
                'last_name': 'Harris',
                'email': 'grace.harris@example.com',
                'phone_number': '9990001111',
                'address': '606 Willow St, Anytown, USA',
                'date_of_birth': '1999-09-09',
                'password': 'password123',
            },
            {
                'username': 'worker10',
                'first_name': 'Henry',
                'last_name': 'Irvine',
                'email': 'henry.irvine@example.com',
                'phone_number': '2223334444',
                'address': '707 Aspen St, Othertown, USA',
                'date_of_birth': '2000-10-10',
                'password': 'password123',
            }
        ]

        for worker_data in workers_to_insert:
            user, created = User.objects.get_or_create(
                username=worker_data['username'],
                defaults={
                    'email': worker_data['email'],
                    'password': worker_data['password'],
                }
            )
            if created:
                user.set_password(worker_data['password'])
                user.save()
                self.stdout.write(self.style.SUCCESS(
                    f'Successfully created user: {worker_data["username"]}'))
            else:
                self.stdout.write(self.style.WARNING(
                    f'User already exists: {worker_data["username"]}'))

            _, created = Worker.objects.get_or_create(
                user=user,
                defaults={
                    'first_name': worker_data['first_name'],
                    'last_name': worker_data['last_name'],
                    'email': worker_data['email'],
                    'phone_number': worker_data['phone_number'],
                    'address': worker_data['address'],
                    'date_of_birth': worker_data['date_of_birth'],
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(
                    f'Successfully added worker: {worker_data["username"]}'))
            else:
                self.stdout.write(self.style.WARNING(
                    f'Worker already exists for: {worker_data["username"]}'))
