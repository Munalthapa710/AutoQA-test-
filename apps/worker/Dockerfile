FROM mcr.microsoft.com/playwright/python:v1.54.0-jammy

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/workspace/apps/api:/workspace/apps/worker:/workspace/packages/python

WORKDIR /workspace

COPY requirements-worker.txt /workspace/requirements-worker.txt
RUN pip install --no-cache-dir -r /workspace/requirements-worker.txt

COPY . /workspace

CMD ["python", "-m", "worker.main"]
