"""元数据路由：健康检查、运行模式、演示客户"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Customer
from ..services.auth_service import get_current_staff

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("/health")
def health():
    return {"ok": True}


@router.get("/mode")
def mode():
    return {"mock": settings.is_mock, "model": settings.model,
            "provider": settings.provider}


@router.get("/customers")
def customers(db: Session = Depends(get_db), _staff=Depends(get_current_staff)):
    rows = db.query(Customer).order_by(Customer.id).all()
    return {"items": [{"id": c.id, "name": c.name, "level": c.level,
                       "phone": c.phone} for c in rows]}
