"""数据分析路由"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import analytics_service, learning_service

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    return analytics_service.overview(db)


@router.get("/trends")
def trends(days: int = 30, db: Session = Depends(get_db)):
    return analytics_service.trends(db, days=min(days, 90))


@router.get("/hot-issues")
def hot_issues(days: int = 30, db: Session = Depends(get_db)):
    return {"items": learning_service.hot_issue_tags(db, days=days)}


@router.get("/distribution")
def distribution(db: Session = Depends(get_db)):
    return analytics_service.distribution(db)
