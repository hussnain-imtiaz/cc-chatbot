# Use a slim Python 3.11 base - smaller image, faster pulls
FROM python:3.11-slim

# stop Python from writing .pyc files and buffer stdout (better for container logs)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# install uv - the same package manager used in local dev
RUN pip install uv --no-cache-dir

WORKDIR /app

# copy dependency files first so Docker can cache this layer
# if you only change app code, Docker won't reinstall packages
COPY pyproject.toml .
COPY README.md .

# install all dependencies (no dev extras in production)
RUN uv sync --no-dev

# copy the full project
COPY . .

# create the llmops folder so the tracer can write traces.db
# in production this is supplemented by Application Insights
RUN mkdir -p llmops

# expose Streamlit default port
EXPOSE 8501

# health check so Azure knows the app is ready
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# run the app
# --server.address=0.0.0.0 is required so Azure can reach the container
CMD ["uv", "run", "streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
