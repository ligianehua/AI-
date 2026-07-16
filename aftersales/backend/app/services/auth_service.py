"""认证与权限：密码哈希、token 签发校验、FastAPI 依赖"""
import hashlib
import secrets

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuthToken, Customer, Staff

ROLE_NAMES = {"admin": "管理员", "agent": "客服", "ops": "知识运营"}


# ---------- 密码 ----------

def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, _ = stored.split("$", 1)
    except ValueError:
        return False
    return secrets.compare_digest(hash_password(password, salt), stored)


# ---------- token ----------

def issue_token(db: Session, kind: str, ref_id: int) -> str:
    token = secrets.token_hex(24)
    db.add(AuthToken(token=token, kind=kind, ref_id=ref_id))
    db.commit()
    return token


def revoke_token(db: Session, token: str):
    db.query(AuthToken).filter(AuthToken.token == token).delete()
    db.commit()


def _extract_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return authorization.strip()


# ---------- FastAPI 依赖 ----------

def get_current_customer(authorization: str | None = Header(None),
                         db: Session = Depends(get_db)) -> Customer:
    token = _extract_token(authorization)
    if token:
        row = db.query(AuthToken).filter(AuthToken.token == token,
                                         AuthToken.kind == "customer").first()
        if row:
            customer = db.query(Customer).get(row.ref_id)
            if customer:
                return customer
    raise HTTPException(401, "请先登录（客户）")


def get_current_staff(authorization: str | None = Header(None),
                      db: Session = Depends(get_db)) -> Staff:
    token = _extract_token(authorization)
    if token:
        row = db.query(AuthToken).filter(AuthToken.token == token,
                                         AuthToken.kind == "staff").first()
        if row:
            staff = db.query(Staff).get(row.ref_id)
            if staff:
                return staff
    raise HTTPException(401, "请先登录（员工）")


def get_actor(authorization: str | None = Header(None),
              db: Session = Depends(get_db)) -> tuple[str, Customer | Staff]:
    """客户或员工皆可访问的端点用这个；返回 (kind, obj)"""
    token = _extract_token(authorization)
    if token:
        row = db.query(AuthToken).filter(AuthToken.token == token).first()
        if row:
            if row.kind == "customer":
                c = db.query(Customer).get(row.ref_id)
                if c:
                    return "customer", c
            else:
                s = db.query(Staff).get(row.ref_id)
                if s:
                    return "staff", s
    raise HTTPException(401, "请先登录")


def require_roles(*roles: str):
    """角色守卫：admin 永远放行"""
    def dep(staff: Staff = Depends(get_current_staff)) -> Staff:
        if staff.role != "admin" and staff.role not in roles:
            need = "/".join(ROLE_NAMES.get(r, r) for r in roles)
            raise HTTPException(403, f"没有权限（需要 {need} 或管理员角色）")
        return staff
    return dep


# ---------- 种子员工 ----------

DEFAULT_STAFF = [
    ("admin", "admin123", "系统管理员", "admin"),
    ("agent1", "agent123", "客服小王", "agent"),
    ("ops1", "ops123", "知识运营小李", "ops"),
]


def seed_staff(db: Session):
    if db.query(Staff).count() > 0:
        return
    for username, password, name, role in DEFAULT_STAFF:
        db.add(Staff(username=username, password_hash=hash_password(password),
                     display_name=name, role=role))
    db.commit()
