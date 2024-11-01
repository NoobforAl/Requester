PYTHON := uv run

run: create_migrate
	cd ./src && $(PYTHON) manage.py runserver

deploy:
	rm -f ./requirement.txt ./src/db.sqlite3
	pipenv requirements > requirement.txt

	cd ./src && \
		gunicorn -w 10 requester.wsgi:application

create_migrate:
	cd ./src && $(PYTHON) manage.py migrate

create_makemigrations:
	cd ./src && $(PYTHON) manage.py makemigrations offer
	cd ./src && $(PYTHON) manage.py makemigrations worker

create_super_user: create_migrate
	cd ./src && $(PYTHON) manage.py createsuperuser

database_diagram: create_migrate
	$(PYTHON) src/manage.py graph_models -a -g -o test.png
