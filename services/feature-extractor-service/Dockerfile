FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY services/feature-extractor-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/__init__.py ./services/__init__.py
COPY services/shared ./services/shared
COPY services/feature-extractor-service/app ./app

EXPOSE 8013

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8013"]

