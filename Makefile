PYTHON := uv run

.PHONY: help run deploy create_migrate create_makemigrations create_super_user database_diagram insert_mock_data

help:
	@echo "Usage:"
	@echo "  make run                   - Run the Django development server"
	@echo "  make deploy                - Deploy the application"
	@echo "  make create_migrate        - Apply database migrations"
	@echo "  make create_makemigrations - Create new database migrations"
	@echo "  make create_super_user     - Create a new Django superuser"
	@echo "  make database_diagram      - Generate a database diagram"
	@echo "  make insert_mock_data      - Insert mock data into the database"

run: create_migrate
	cd ./src && $(PYTHON) manage.py runserver

run_docker_compose:
	@echo "Running docker compose"
	rm -f ./requirement.txt ./src/db.sqlite3
	uv pip freeze  > requirements.txt 
	docker-compose up --build

deploy: create_migrate insert_mock_data
	@echo "Deploying the application"
	@sleep 10
	
	@echo "Creating super user"
	cd ./src && $(PYTHON) manage.py shell -c "from django.contrib.auth.models import User; User.objects.filter(username='admin').delete(); User.objects.create_superuser('admin', 'admin@example.com', 'admin')"
	
	@echo "Starting gunicorn"
	cd ./src && gunicorn -w 10 --bind 0.0.0.0:8000 requester.wsgi:application

create_migrate:
	cd ./src && $(PYTHON) manage.py migrate

create_makemigrations:
	cd ./src && $(PYTHON) manage.py makemigrations offer
	cd ./src && $(PYTHON) manage.py makemigrations worker

create_super_user: create_migrate
	cd ./src && $(PYTHON) manage.py createsuperuser

database_diagram: create_migrate
	$(PYTHON) src/manage.py graph_models -a -g -o test.png

insert_mock_data: create_migrate
	@echo "Inserting mock data"
	@echo "Inserting mock data for offers"
	cd ./src && sh ./scripts/insert_offers.sh

	@echo "Inserting mock data for workers"
	cd ./src && sh ./scripts/insert_workers.sh

	@echo "Inserting mock data for tags"
	cd ./src && sh ./scripts/insert_tags.sh

	@echo "Inserting mock data for jobs"
	cd ./src && sh ./scripts/insert_jobs.sh

	@echo "Inserting mock data for applications"
	cd ./src && sh ./scripts/insert_applications.sh

