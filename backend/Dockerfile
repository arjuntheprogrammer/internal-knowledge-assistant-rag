FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    build-essential \
    tesseract-ocr \
    libtesseract-dev \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/* \
    && pip install uv \
    && uv pip install --system -r requirements.txt

COPY . .

CMD ["sh", "-c", "flask run --host=0.0.0.0 --port=${PORT:-5001}"]
