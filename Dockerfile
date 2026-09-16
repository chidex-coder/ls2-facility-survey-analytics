# Dash edition of the LS 2.0 dashboard (works on Render, Fly.io, Hugging Face Spaces, any container host)
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
COPY . .
ENV PORT=8050
EXPOSE 8050
CMD gunicorn src.dashboard.dash_app:server --bind 0.0.0.0:${PORT} --workers 2 --threads 4 --timeout 120
