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
from sqlalchemy import text
from app.database import engine
settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE resumes ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id)"))
        await conn.execute(text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id)"))
        await conn.execute(text("ALTER TABLE interview_sessions ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id)"))
    print("Migration done")
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
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
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
