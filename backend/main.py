from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.cloud import ensure_cloud_root
from app.database import init_db
from app.database import SessionLocal
from app.services import ensure_digital_employees, ensure_team_members, scan_knowledge_directory
from app.routes.agents import router as agents_router
from app.routes.boss import router as boss_router
from app.routes.dashboard import router as dashboard_router
from app.routes.designers import router as designers_router
from app.routes.health import router as health_router
from app.routes.inbox import router as inbox_router
from app.routes.knowledge import router as knowledge_router
from app.routes.projects import router as projects_router
from app.routes.team import router as team_router
from app.routes.tech_points import router as tech_points_router
from app.routes.agent_chat import router as agent_chat_router
from app.routes.image_gen import router as image_gen_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # === startup ===
    init_db()
    settings.upload_root_path.mkdir(parents=True, exist_ok=True)
    ensure_cloud_root()
    db = SessionLocal()
    try:
        ensure_digital_employees(db)
        ensure_team_members(db)
        # 索引内置知识库资产（如甲方黑话词典），确保运行时检索可用
        knowledge_assets_path = Path(__file__).resolve().parent / "knowledge_assets"
        if knowledge_assets_path.is_dir():
            scan_knowledge_directory(db, knowledge_assets_path)
    finally:
        db.close()
    yield
    # === shutdown ===（预留清理位）

app = FastAPI(
    title="RMO-Ai Backend",
    description="以 Project 为中心的智能设计工作台后端",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5175",
        "http://localhost:5175",
        "http://127.0.0.1:5176",
        "http://localhost:5176",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(projects_router)
app.include_router(inbox_router)
app.include_router(knowledge_router)
app.include_router(agents_router)
app.include_router(designers_router)
app.include_router(dashboard_router)
app.include_router(team_router)
app.include_router(boss_router)
app.include_router(tech_points_router)
app.include_router(agent_chat_router, prefix="/api", tags=["agent-chat"])
app.include_router(image_gen_router, prefix="/api", tags=["image-generation"])

