from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from autoqa_shared.settings import get_settings

from .api.routes import configs, generated_tests, health, runs


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    settings.artifacts_root.mkdir(parents=True, exist_ok=True)
    settings.generated_tests_root.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="autoqa-agent API", lifespan=lifespan)
settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(configs.router)
app.include_router(runs.router)
app.include_router(generated_tests.router)

app.mount("/files/artifacts", StaticFiles(directory=str(settings.artifacts_root)), name="artifacts")
app.mount("/files/generated-tests", StaticFiles(directory=str(settings.generated_tests_root)), name="generated-tests")
