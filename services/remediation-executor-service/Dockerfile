FROM python:3.12-slim

WORKDIR /app
COPY services/remediation-executor-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/__init__.py ./services/__init__.py
COPY services/shared ./services/shared
COPY services/remediation-executor-service/app ./app

ENV PYTHONPATH=/app
EXPOSE 8023
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8023"]

