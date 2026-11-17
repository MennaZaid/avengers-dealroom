# One image for the API, the UI and the one-off seed job.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first so code edits don't reinstall everything.
COPY pyproject.toml ./
COPY src/venture_os/__init__.py src/venture_os/__init__.py
RUN pip install -e ".[ui]"

COPY . .

EXPOSE 8000 8501
CMD ["uvicorn", "venture_os.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
