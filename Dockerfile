FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 3005

CMD ["sh", "-c", "uvicorn realtime_server:app --host 0.0.0.0 --port ${PORT:-3005}"]