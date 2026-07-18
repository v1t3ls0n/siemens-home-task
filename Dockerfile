FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
# shell form so $PORT (injected by Railway/most PaaS) is honoured; 8000 locally.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
