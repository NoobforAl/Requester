PYTHON := python

.PHONY: help run

help:
	@echo "Usage:"
	@echo "  make run                   - Run the Django development server"

run:
	@echo "Running the Django development server"

	@echo "Create Only Folder for data"
	mkdir -p es_data mysql_data redis_data ollama_data

	@echo "Restore Static"
	cd ./src && $(PYTHON) manage.py collectstatic --skip-checks --no-input

	@echo "Down docker compose"
	docker-compose down

	@echo "Running docker compose"
	rm -f ./requirement.txt ./src/db.sqlite3
	pipenv requirements > requirements.txt 
	docker-compose up -d --build	

deploy: create_migrate create_makemigrations create_es_fields insert_mock_data create_super_user
	@echo "Deploying the application"	

	@echo "Starting Dev Server"
	export DJANGO_DEBUG=True
	cd ./src && $(PYTHON) manage.py runserver 0.0.0.0:8000

	# only for production
	# cd ./src && gunicorn -w 10 --bind 0.0.0.0:8000 requester.wsgi:application

setup_celery: create_migrate create_makemigrations create_es_fields
	cd ./src && celery -A requester worker --loglevel=info

create_migrate:
	cd ./src && $(PYTHON) manage.py migrate

create_makemigrations:
	cd ./src && $(PYTHON) manage.py makemigrations offer
	cd ./src && $(PYTHON) manage.py makemigrations worker

create_super_user: create_migrate
	@echo "Creating super user default admin/admin"
	cd ./src && $(PYTHON) manage.py shell -c "from django.contrib.auth.models import User; User.objects.filter(username='admin').delete(); User.objects.create_superuser('admin', 'admin@example.com', 'admin')"

database_diagram: create_migrate
	$(PYTHON) src/manage.py graph_models -a -g -o test.png

create_es_fields: create_migrate
	@echo "Creating elasticsearch fields"
	cd ./src && $(PYTHON) manage.py search_index --rebuild -f

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


clean: 
	@echo "Down docker compose"
	docker-compose down

	@echo "Cleaning up"
	sudo rm -rf es_data mysql_data redis_data ollama_data
