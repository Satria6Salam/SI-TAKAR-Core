from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from database.config import get_db
from database.models import Admin, UMKM
from routers.admin_security import (
    SESSION_COOKIE,
    SESSION_TTL_SECONDS,
    create_session_token,
    get_admin_session,
    require_admin,
    verify_password,
)

router = APIRouter(tags=["Admin"])
TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"


class AdminLogin(BaseModel):
    username: str
    password: str


@router.get("/admin/login", include_in_schema=False)
def admin_login_page(request: Request, db: Session = Depends(get_db)):
    if get_admin_session(request, db):
        return RedirectResponse("/admin", status_code=303)
    return FileResponse(TEMPLATES_DIR / "admin_login.html")


@router.post("/admin/login")
def admin_login(data: AdminLogin, request: Request, db: Session = Depends(get_db)):
    admin = db.query(Admin).filter(Admin.username == data.username).first()
    if admin is None or not verify_password(data.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Username atau password tidak sesuai")

    response = JSONResponse({"ok": True, "redirect": "/admin"})
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(admin.username),
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/",
    )
    return response


@router.post("/admin/logout")
def admin_logout():
    response = JSONResponse({"ok": True, "redirect": "/admin/login"})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/admin", include_in_schema=False)
@router.get("/admin.html", include_in_schema=False)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    if get_admin_session(request, db) is None:
        return RedirectResponse("/admin/login", status_code=303)
    return FileResponse(TEMPLATES_DIR / "admin.html")


@router.get("/admin/ringkasan")
def admin_summary(db: Session = Depends(get_db), _admin: Admin = Depends(require_admin)):
    counts = dict(
        db.query(UMKM.status_pendaftaran, func.count(UMKM.id))
        .group_by(UMKM.status_pendaftaran)
        .all()
    )
    return {"total": sum(counts.values()), "status": counts}