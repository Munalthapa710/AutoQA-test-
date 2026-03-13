$env:PYTHONPATH = "C:\Users\hp\QA-GPT\.pydeps;C:\Users\hp\QA-GPT\packages\python;C:\Users\hp\QA-GPT\apps\api;C:\Users\hp\QA-GPT\apps\worker"
$env:DATABASE_URL = "sqlite:///C:/Users/hp/QA-GPT/artifacts/reports/autoqa-local.db"
$env:ARTIFACTS_ROOT = "C:/Users/hp/QA-GPT/artifacts"
$env:GENERATED_TESTS_ROOT = "C:/Users/hp/QA-GPT/generated-tests"
$env:REDIS_URL = "redis://localhost:6379/0"

Set-Location "C:\Users\hp\QA-GPT"
python -m worker.main
