FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --default-timeout=120 -r requirements.txt

COPY . .

CMD ["sh", "-c", "flask run --host=0.0.0.0 --port=${PORT:-5001}"]
