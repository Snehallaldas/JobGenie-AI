from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.config import get_settings
from app.database import init_db
from app.routers import resume as resume_router
from app.routers import jobs as jobs_router
from app.routers import interview as interview_router
from app.routers import auth as auth_router
from app.models import resume as resume_model
from app.models import job as job_model
from app.models import interview as interview_model
from app.models import user as user_model

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    print("Database initialized")
    yield
    print("Shutting down")

app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router, prefix="/api/auth", tags=["Auth"])
app.include_router(resume_router.router, prefix="/api/resume", tags=["Resume"])
app.include_router(jobs_router.router, prefix="/api/jobs", tags=["Jobs"])
app.include_router(interview_router.router, prefix="/api/interview", tags=["Interview"])

@app.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.APP_NAME}