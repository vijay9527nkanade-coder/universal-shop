# FastAPI + PostgreSQL Backend

## Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app entry point
│   ├── config.py        # Settings via pydantic-settings + env vars
│   ├── database.py      # SQLAlchemy engine, session, Base
│   ├── models.py        # ORM models
│   ├── schemas.py       # Pydantic request/response schemas
│   └── routers/
│       ├── __init__.py
│       └── items.py     # Example CRUD router
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/        # Generated migration files go here
├── alembic.ini
├── requirements.txt
└── .env.example
```

## Quick Start

### 1. Create and activate a virtual environment

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
# Edit .env with your PostgreSQL credentials
```

### 4. Run database migrations

```bash
# Generate the first migration
alembic revision --autogenerate -m "initial"

# Apply migrations
alembic upgrade head
```

### 5. Start the development server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs available at: http://localhost:8000/docs

## Environment Variables

| Variable          | Default                                              | Description                     |
|-------------------|------------------------------------------------------|---------------------------------|
| `DATABASE_URL`    | `postgresql://myuser:mypassword@localhost:5432/mydb` | Full PostgreSQL connection URL   |
| `DATABASE_HOST`   | `localhost`                                          | Postgres host                   |
| `DATABASE_PORT`   | `5432`                                               | Postgres port                   |
| `DATABASE_NAME`   | `mydb`                                               | Database name                   |
| `DATABASE_USER`   | `myuser`                                             | Database user                   |
| `DATABASE_PASSWORD` | `mypassword`                                       | Database password               |
| `SECRET_KEY`      | `change-me-in-production`                            | App secret key                  |
| `APP_ENV`         | `development`                                        | Environment name                |
| `DEBUG`           | `true`                                               | Enable debug mode & SQL logging |
