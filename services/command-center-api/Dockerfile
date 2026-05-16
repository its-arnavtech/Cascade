FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY services/command-center-api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY services/command-center-api/app /app/app

EXPOSE 8031
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8031"]
