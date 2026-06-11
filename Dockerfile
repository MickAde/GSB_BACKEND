FROM python:3.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# System dependencies:
#   gcc, libpq-dev      → compile psycopg2
#   tesseract-ocr       → required by pytesseract for handwritten/scanned note OCR
#   tesseract-ocr-eng   → English language data pack
#   libjpeg-dev, zlib1g-dev, libpng-dev → Pillow image support
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       gcc libpq-dev \
       tesseract-ocr tesseract-ocr-eng \
       libjpeg-dev zlib1g-dev libpng-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# Default command — overridden per-service in docker-compose.yaml
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
