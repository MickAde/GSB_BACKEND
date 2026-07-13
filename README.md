# README

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**GSB_Project** is a Django 5.2 REST API backend for managing schools and users. It uses PostgreSQL (Supabase) for production and SQLite for local development. The project follows Django's MVT (Model-View-Template) architecture with three custom apps: `schools`, `users`, and `core`.

### Tech Stack
- **Framework**: Django 5.2.15
- **REST API**: Django REST Framework 3.17.1
- **Database**: PostgreSQL (via psycopg2) or SQLite (local)
- **Python**: 3.14
- **Containerization**: Docker & Docker Compose
- **Environment Config**: python-decouple

### Key Libraries
- `asgiref==3.11.1` - ASGI utilities
- `sqlparse==0.5.5` - SQL parsing
- `tzdata==2026.2` - Timezone data
- `psycopg2-binary==2.9.12` - PostgreSQL adapter

## Directory Structure

```
GSB_Project/
├── GSB_Project/           # Project configuration (Django settings, URLs, WSGI/ASGI)
│   ├── settings.py        # Main configuration (apps, middleware, database, static files)
│   ├── urls.py            # Root URL configuration (only admin panel configured)
│   ├── wsgi.py            # WSGI entry point
│   └── asgi.py            # ASGI entry point
├── core/                  # Core app (foundational functionality)
│   ├── models.py          # [Empty - to be defined]
│   ├── views.py           # [Empty - to be defined]
│   ├── admin.py           # Admin registration
│   └── migrations/        # Database migrations
├── schools/               # Schools management app
│   ├── models.py          # [Empty - to be defined]
│   ├── views.py           # [Empty - to be defined]
│   ├── admin.py           # Admin registration
│   └── migrations/        # Database migrations
├── users/                 # Users management app
│   ├── models.py          # [Empty - to be defined]
│   ├── views.py           # [Empty - to be defined]
│   ├── admin.py           # Admin registration
│   └── migrations/        # Database migrations
├── manage.py              # Django CLI utility
├── requirements.txt       # Python dependencies
├── Dockerfile             # Docker image configuration
├── docker-compose.yaml    # Local development container orchestration
├── db.sqlite3             # Local SQLite database
├── .env.local             # Local development environment variables
└── .env.production        # Production environment variables
```

## Database Configuration

The project supports two database backends controlled by the `DB_ENGINE` environment variable:

- **SQLite** (default): Used for local development. Database file: `db.sqlite3`
- **PostgreSQL**: Used for production (Supabase). Requires SSL connection with environment variables:
  - `DB_ENGINE=postgres`
  - `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`

Connection pooling is enabled for PostgreSQL (`CONN_MAX_AGE=600`).

## Setup and Development

### Prerequisites
- Python 3.14+
- Virtual environment (venv) already set up in `./venv`
- Docker & Docker Compose (optional, for containerized development)

### Initial Setup
```bash
# Activate virtual environment (Windows)
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create database and apply migrations
python manage.py migrate
```

### Running the Development Server
```bash
# Option 1: Direct Python (uses SQLite by default)
python manage.py runserver

# Option 2: Docker Compose (with hot-reloading)
docker-compose up

# Server runs at http://localhost:8000
```

### Database Operations
```bash
# Create new migration for model changes
python manage.py makemigrations

# Apply migrations to database
python manage.py migrate

# Rollback to specific migration
python manage.py migrate <app_name> <migration_name>

# Create superuser for admin access
python manage.py createsuperuser

# Access Django admin at http://localhost:8000/admin/
```

## Architecture Notes

### App Structure
- **core**: Foundational functionality shared across apps
- **schools**: School entities and management
- **users**: User accounts and authentication
- **GSB_Project**: Project-level configuration and URL routing

### Current State
The project is in early development. Models and views are placeholders in all three apps. The URL configuration only includes the admin panel (`/admin/`). Additional endpoints need to be implemented.

### Configuration Management
Environment variables are loaded using `python-decouple.config()`. The `DEBUG` flag is controlled via environment variable and defaults to `True` for development.

## Testing

Currently, test.py files exist in each app but are empty. Django's standard testing framework is available via:
```bash
python manage.py test
```

Tests can be run per app:
```bash
python manage.py test core
python manage.py test schools
python manage.py test users
```

## Docker Deployment

### Local Development with Docker
```bash
docker-compose up
```
- Builds Docker image from Dockerfile
- Mounts local code for hot-reloading
- Exposes port 8000
- Uses `.env.local` for configuration

### Production Docker Build
```bash
docker build -t gsb-project:latest .
docker run -p 8000:8000 --env-file .env.production gsb-project:latest
```

The Dockerfile uses Python 3.14-slim and includes system dependencies for PostgreSQL driver compilation.

## Important Considerations

- **Models**: All three apps (core, schools, users) have empty models. Before adding business logic, design the data model carefully.
- **URL Routing**: Currently only the Django admin is routed. Additional app-level URL configurations need to be created.
- **DRF Integration**: Django REST Framework is installed but not yet integrated. Ensure API views and serializers are properly implemented.
- **Security**: 
  - `ALLOWED_HOSTS` is empty (needs configuration for production)
  - `SECRET_KEY` uses a placeholder in development (ensure it's secure in production)
  - Use environment variables for all sensitive credentials

