# Dash edition of the LS 2.0 dashboard.
# Works unchanged on Hugging Face Spaces (sdk: docker, app_port: 8050), Render, Fly.io or any container host.
FROM python:3.12-slim

# Hugging Face Spaces run the container as UID 1000; give that user the app directory.
RUN useradd -m -u 1000 appuser
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
COPY --chown=appuser:appuser . .
USER appuser

ENV PORT=8050
EXPOSE 8050
CMD gunicorn src.dashboard.dash_app:server --bind 0.0.0.0:${PORT} --workers 2 --threads 4 --timeout 120
