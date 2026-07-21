# SEMA REST API (FastAPI) -- development container.
#
# Built for LOCAL DEV, not deployment: the source tree is bind-mounted over
# /app by docker-compose.yml and uvicorn runs with --reload, so editing a
# .py file on Windows restarts the server inside the container.
#
# Dependencies are installed in their own layer (before the source is copied)
# so editing code does NOT invalidate the pip cache and trigger a reinstall.

FROM python:3.12-slim

# Faster, quieter installs; no .pyc clutter in the bind-mounted source tree.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# We install the FULL requirements.txt (not just the API's subset) even though
# the backend is framework-free and never needs Streamlit at runtime. Keeping
# one dependency list avoids drift between the venv and the container; the
# extra image size is irrelevant for local development.
COPY requirements.txt requirements-api.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-api.txt

# Editable install of sema_core + api, matching the venv setup documented in
# pyproject.toml -- imports resolve with no PYTHONPATH or sys.path hacks.
# --no-deps because everything is already installed above.
COPY pyproject.toml ./
COPY sema_core ./sema_core
COPY api ./api
RUN pip install --no-cache-dir -e . --no-deps

EXPOSE 8000

# --host 0.0.0.0 so the port is reachable from the Windows host; the default
# 127.0.0.1 would only listen inside the container's own network namespace.
CMD ["uvicorn", "api.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"]
