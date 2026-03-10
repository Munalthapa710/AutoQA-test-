FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/workspace/apps/api:/workspace/packages/python

WORKDIR /workspace

COPY requirements-api.txt /workspace/requirements-api.txt
RUN pip install --no-cache-dir -r /workspace/requirements-api.txt

COPY . /workspace

CMD ["uvicorn", "app.main:app", "--app-dir", "/workspace/apps/api", "--host", "0.0.0.0", "--port", "8000"]
