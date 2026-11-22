# Requester

Requester is a job recruitment platform designed as a college project. The platform allows workers to search and apply for jobs, while companies can post job offers and manage applications. The project is built using Django and leverages Docker for containerization.

## Class Diagrams

The class diagram for the project outlines the main entities and their relationships:

- **User**: Represents a user of the platform, which can be either a worker or a company offering jobs.
- **Worker**: Contains personal information about the worker, such as name, email, phone number, address, and date of birth.
- **JobRequest**: Represents a job application submitted by a worker, including the resume, cover letter, status, and timestamps.
- **Offer**: Represents a job offer posted by a company, including company details and job information.
- **Job**: Represents a job listing, including job name, details, and timestamps.
- **Tag**: Represents tags associated with jobs for categorization.

The relationships between these entities are as follows:

- A User can have one Worker profile and one Offer profile.
- A Worker can submit multiple JobRequests.
- A Job can receive multiple JobRequests.
- An Offer can post multiple Jobs.
- A Job can be tagged with multiple Tags.

![Class Diagram](diagram/class_diagram.png)

## Use Case Diagrams

The use case diagram illustrates the interactions between different actors (Worker, Offer, Admin) and the system:

- **Worker Use Cases**:
  - Login
  - Logout
  - Register
  - View Jobs
  - Apply for Job
  - Update Profile

- **Offer Use Cases**:
  - Login
  - Logout
  - Register
  - Create Job
  - View Job Applications
  - Update Job Status
  - Update Profile

- **Admin Use Cases**:
  - Manage Users
  - Manage Jobs
  - Manage Offers

![Use Case Diagram](diagram/use_case_diagram.png)

## Sequence Diagram

The sequence diagram below illustrates the interactions between different actors (Worker, Employer, Admin) and the system:

- **Worker**:
  - Logs into the system.
  - Views job postings.
  - Submits job applications (resume and cover letter).

- **Employer**:
  - Creates new job postings.
  - Views job applications.

- **Admin**:
  - Manages users.
  - Manages job postings.
  - Manages employers.

![Sequence Diagram](diagram/sequence_diagram.png)

## Activity Diagram

The activity diagram below shows the workflow of the job application process:

- **Worker**:
  - Registers on the platform.
  - Searches for job postings.
  - Applies for a job.

- **Employer**:
  - Posts a new job.
  - Reviews job applications.
  - Updates job status.

- **Admin**:
  - Oversees platform activities.
  - Manages user accounts.
  - Manages job postings.

![Activity Diagram](diagram/activity_diagram.png)

## Required Tools

To run and develop this project, you will need the following tools:

- **Docker**: Used for containerizing the application and its dependencies.
- **Docker Compose**: Used to define and run multi-container Docker applications.
- **Python 3.12**: The programming language used for the project.
- **uv**: Used as the Python package and project manager (`uv sync` installs dependencies from `pyproject.toml` / `uv.lock`).
- **Django**: The web framework used to build the application.
- **MariaDB**: The database used to store application data.
- **Redis**: Used for caching and message brokering.
- **Elasticsearch**: The Search engin service.
- **MmailServer**: The TestMail service.
- **Ollama**: The LLM service.

## Makefile Commands

### Usage

- `make dev` - run the dev server on SQLite (no Docker needed)
- `make fix` - format everything, run all linters, type check and tests
- `make clean` - remove caches and build artifacts
- `make docker-up` - start the dev stack in Docker (MariaDB, Redis, Elasticsearch, Ollama); uses `docker-compose.yaml` + `docker-compose.dev.yaml`
- `make test-mariadb` - run the tests against a real MariaDB started from compose
- `make help` - list every command

## Docker: development and production

`docker-compose.dev.yaml` is a development override (`make docker-up` uses it): `DJANGO_DEBUG` on, the Django dev server, mock data, and an admin login `admin` / `admin`. Never use it for a real deployment.

`docker compose up -d --build` with only `docker-compose.yaml` is production-like:

- `DJANGO_DEBUG` is off, so Django refuses to start unless `SECRET_KEY` is set (export it or put it in a `.env` file).
- `ALLOWED_HOSTS` defaults to `localhost,127.0.0.1`; set it to your domain.
- It runs gunicorn after `collectstatic`, and no demo data or demo accounts are created. The seed commands (`insert_offers`, `insert_workers`) refuse to run with `DJANGO_DEBUG` off.
- An admin user is created only if `DJANGO_SUPERUSER_PASSWORD` is set (optionally `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL`). An existing admin's password is never reset.
- Session and CSRF cookies are `Secure` when debug is off: serve the site over HTTPS (set `BEHIND_PROXY=true` behind a TLS proxy), or set `SECURE_COOKIES=false` for a plain-HTTP test.

Database settings are `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` (MariaDB). Without `DB_NAME`, the app uses SQLite.

