"""
main_app: Yakuniy AI reportlarni ko'rsatish va Assistant Telegram Login jarayonlarini 
boshqarish uchun FastAPI Web API.

Ishga tushirish: uvicorn main_app.api:app --reload
"""
from typing import Dict, Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from fastapi.responses import RedirectResponse

from fastapi.templating import Jinja2Templates

from shared.local_db import ensure_assistant_tg_info_table_exists, ensure_ai_reports_table_exists, ensure_group_check_logs_table_exists, ensure_student_issues_log_table_exists, ensure_tracking_table_exists, ensure_inactive_assistants_table_exists
from shared.logger import get_logger

from .tg_auth import router as tg_auth_router
from .api import api_router

logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ilova ishga tushganda assistant_tg_info (SQLite) jadvali mavjudligini kafolatlaydi --
    shu orqali /telegram/assistant/* endpoint'lari /run-stream chaqirilishidan oldin
    ham xatosiz ishlaydi."""
    ensure_tracking_table_exists()
    ensure_ai_reports_table_exists()
    ensure_assistant_tg_info_table_exists()
    ensure_group_check_logs_table_exists()
    ensure_student_issues_log_table_exists()
    ensure_inactive_assistants_table_exists()
    yield



app = FastAPI(title="Manager Agent v4", version="4.0.0", lifespan=lifespan)
app.include_router(tg_auth_router)
app.include_router(api_router)

app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="frontend/templates")

# Telegram login jarayoni uchun aktiv vaqtinchalik sessiyalar kesh-xotirasi
active_login_sessions: Dict[str, Dict[str, Any]] = {}



@app.get("/", tags=["home"], response_class=HTMLResponse)
async def home(request: Request):
    return RedirectResponse(url="/dashboard", status_code=307)
    # return templates.TemplateResponse(request=request, name="group_check.html", context={"active_page": "group-check"})
@app.get("/group-check", tags=["Check"], response_class=HTMLResponse)
async def group_check_page(request: Request):
    return templates.TemplateResponse(request=request, name="group_check.html", context={"active_page": "group-check"})
@app.get("/assistants", tags=["Assistants"], response_class=HTMLResponse)
async def assistants_page(request: Request):
    return templates.TemplateResponse(request=request, name="assistants.html", context={"active_page": "assistants"})

@app.get("/assistant-reports", tags=["Assistant Reports"], response_class=HTMLResponse)
async def assistant_reports_page(request: Request):
    return templates.TemplateResponse(request=request, name="assistant-reports.html", context={"active_page": "assistant-reports"})

@app.get("/assistant/{assistant_id}", tags=["Assistant Detail"], response_class=HTMLResponse)
async def assistant_detail_page(request: Request, assistant_id: int):
    return templates.TemplateResponse(request=request, name="assistant-detail.html", context={"active_page": "assistants", "assistant_id": assistant_id})

@app.get("/connect-tg", tags=["Telegram Connection"], response_class=HTMLResponse)
async def telegram_connection_page(request: Request):
    return templates.TemplateResponse(request=request, name="tg_auth.html", context={"active_page": "connect-tg"})

@app.get("/dashboard", tags=["Dashboard"], response_class=HTMLResponse)
async def dashboard_page(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard.html", context={"active_page": "dashboard"})

@app.get("/settings", tags=["Settings"], response_class=HTMLResponse)
async def settings_page(request: Request):
    return templates.TemplateResponse(request=request, name="settings.html", context={"active_page": "settings"})


@app.get("/settings/inactive-assistant", tags=["Settings"], response_class=HTMLResponse)
async def settings_assistant_page(request: Request):
    return templates.TemplateResponse(request=request, name="settings-inactive-assistant.html", context={"active_page": "settings"})





@app.get("/test", tags=["Home"], response_class=HTMLResponse)
async def test_post(request: Request):
    return templates.TemplateResponse(request=request, name="test-post.html", context={"active_page": "home"})
