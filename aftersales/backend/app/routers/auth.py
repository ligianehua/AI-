"""登录/登出路由"""
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Customer, Staff
from ..services import auth_service
from ..services.auth_service import ROLE_NAMES

router = APIRouter(prefix="/api/auth", tags=["auth"])


class CustomerLogin(BaseModel):
    phone: str
    name: str = ""


class StaffLogin(BaseModel):
    username: str
    password: str


@router.post("/customer/login")
def customer_login(req: CustomerLogin, db: Session = Depends(get_db)):
    phone = req.phone.strip()
    if not phone or len(phone) < 6:
        raise HTTPException(400, "请输入正确的手机号")
    customer = db.query(Customer).filter(Customer.phone == phone).first()
    if not customer:
        name = req.name.strip()
        if not name:
            raise HTTPException(404, "该手机号未注册，请填写姓名完成注册")
        customer = Customer(name=name[:50], phone=phone, level="普通")
        db.add(customer)
        db.commit()
    token = auth_service.issue_token(db, "customer", customer.id)
    return {"token": token,
            "customer": {"id": customer.id, "name": customer.name,
                         "level": customer.level, "phone": customer.phone}}


@router.post("/staff/login")
def staff_login(req: StaffLogin, db: Session = Depends(get_db)):
    staff = db.query(Staff).filter(Staff.username == req.username.strip()).first()
    if not staff or not auth_service.verify_password(req.password, staff.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    token = auth_service.issue_token(db, "staff", staff.id)
    return {"token": token,
            "staff": {"id": staff.id, "username": staff.username,
                      "name": staff.display_name, "role": staff.role,
                      "role_name": ROLE_NAMES.get(staff.role, staff.role)}}


@router.post("/logout")
def logout(authorization: str | None = Header(None), db: Session = Depends(get_db)):
    token = auth_service._extract_token(authorization)
    if token:
        auth_service.revoke_token(db, token)
    return {"ok": True}


@router.get("/demo-accounts")
def demo_accounts(db: Session = Depends(get_db)):
    """演示账号提示（真实部署时删除此接口）"""
    customers = db.query(Customer).order_by(Customer.id).limit(8).all()
    return {
        "customers": [{"phone": c.phone, "name": c.name, "level": c.level} for c in customers],
        "staff": [{"username": u, "password": p, "role_name": ROLE_NAMES[r]}
                  for u, p, _, r in auth_service.DEFAULT_STAFF],
    }
