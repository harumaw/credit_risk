FROM python:3.12-slim

WORKDIR /app

ENV POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    PYTHONPATH=/app/src

RUN pip install poetry

COPY pyproject.toml poetry.lock* ./

RUN poetry install --no-root

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
