"""Application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__ 
from .config import get_settings
from .firebase import init_firebase
from .routers import admin, appointments, auth, content, patients

settings = get_settings()  # fails fast if JWT_SECRET is missing or weak


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_firebase()  # fail at startup, not on the first request
    yield


app = FastAPI(
    title="MIASCS API",
    description="Montalban Infirmary patient and appointment service",
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(patients.router)
app.include_router(appointments.router)
app.include_router(content.router)
app.include_router(admin.router)


@app.get("/api/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "miascs-api"}
