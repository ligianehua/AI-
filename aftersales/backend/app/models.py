"""SQLAlchemy ORM 模型"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def now():
    return datetime.now()


# ---------- 基础数据 ----------

class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    phone: Mapped[str] = mapped_column(String(20), default="")
    email: Mapped[str] = mapped_column(String(100), default="")
    level: Mapped[str] = mapped_column(String(10), default="普通")  # 普通/VIP/SVIP
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    model_no: Mapped[str] = mapped_column(String(50), default="")
    category: Mapped[str] = mapped_column(String(50))
    price: Mapped[float] = mapped_column(Float, default=0)
    warranty_months: Mapped[int] = mapped_column(Integer, default=12)
    return_days: Mapped[int] = mapped_column(Integer, default=7)
    exchange_days: Mapped[int] = mapped_column(Integer, default=15)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_no: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    amount: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(10), default="已付款")  # 已付款/已发货/已签收/已完成
    purchased_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    product: Mapped["Product"] = relationship()
    customer: Mapped["Customer"] = relationship()


# ---------- 认证 ----------

class Staff(Base):
    """员工账号：admin=管理员 / agent=客服 / ops=知识运营"""
    __tablename__ = "staff"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))  # salt$pbkdf2hex
    display_name: Mapped[str] = mapped_column(String(50))
    role: Mapped[str] = mapped_column(String(10), default="agent")  # admin/agent/ops
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class AuthToken(Base):
    __tablename__ = "auth_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(10))  # customer/staff
    ref_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


# ---------- 会话与消息 ----------

class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    channel: Mapped[str] = mapped_column(String(10), default="web")
    status: Mapped[str] = mapped_column(String(10), default="active")  # active/closed
    mode: Mapped[str] = mapped_column(String(10), default="ai")  # ai/human（人工接管中）
    assigned_agent: Mapped[str | None] = mapped_column(String(50), nullable=True)
    title: Mapped[str] = mapped_column(String(100), default="新会话")
    resolved: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # 学习分析回填
    handed_off: Mapped[bool] = mapped_column(Boolean, default=False)
    analyzed: Mapped[bool] = mapped_column(Boolean, default=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON: 摘要/标签/mock状态游标
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    customer: Mapped["Customer"] = relationship()


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(10))  # user/assistant/notice（系统提示条）
    agent_name: Mapped[str | None] = mapped_column(String(50), nullable=True)  # 人工客服回复时记录客服名
    display_text: Mapped[str] = mapped_column(Text, default="")
    image_path: Mapped[str | None] = mapped_column(String(200), nullable=True)  # 客户上传的图片
    feedback: Mapped[str | None] = mapped_column(String(4), nullable=True)  # up/down（AI回答反馈）
    raw_blocks: Mapped[str | None] = mapped_column(Text, nullable=True)  # 完整 API content blocks JSON
    tool_calls: Mapped[str | None] = mapped_column(Text, nullable=True)  # [{name,label,summary}] 前端角标
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


# ---------- 工单 ----------

TICKET_STATUSES = ["待处理", "处理中", "待客户确认", "已解决", "已关闭"]


class Ticket(Base):
    __tablename__ = "tickets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_no: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id"), nullable=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(20), default="其他")  # 故障报修/物流咨询/投诉建议/退换货/其他
    priority: Mapped[str] = mapped_column(String(10), default="中")  # 低/中/高/紧急
    status: Mapped[str] = mapped_column(String(10), default="待处理", index=True)
    assignee: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    customer: Mapped["Customer"] = relationship()


class TicketEvent(Base):
    __tablename__ = "ticket_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(10), nullable=True)
    to_status: Mapped[str] = mapped_column(String(10))
    note: Mapped[str] = mapped_column(Text, default="")
    operator: Mapped[str] = mapped_column(String(20), default="AI助手")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


# ---------- 退换货 RMA ----------

RMA_STATUSES = ["已提交", "已批准", "待寄回", "已收货", "处理中", "已完成", "已驳回", "已取消"]


class RmaRequest(Base):
    __tablename__ = "rma_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rma_no: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id"), nullable=True)
    type: Mapped[str] = mapped_column(String(10))  # 退货/换货/维修
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(10), default="已提交", index=True)
    refund_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    tracking_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    order: Mapped["Order"] = relationship()
    customer: Mapped["Customer"] = relationship()


class RmaEvent(Base):
    __tablename__ = "rma_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rma_id: Mapped[int] = mapped_column(ForeignKey("rma_requests.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(10), nullable=True)
    to_status: Mapped[str] = mapped_column(String(10))
    note: Mapped[str] = mapped_column(Text, default="")
    operator: Mapped[str] = mapped_column(String(20), default="AI助手")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


# ---------- 知识库 ----------

class KbEntry(Base):
    __tablename__ = "kb_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    question: Mapped[str] = mapped_column(Text, default="")
    answer: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(20), default="其他")  # 产品使用/故障排查/退换货政策/保修条款/物流/其他
    tags: Mapped[str] = mapped_column(String(200), default="")
    entry_type: Mapped[str] = mapped_column(String(20), default="faq")  # faq/policy/troubleshooting
    source: Mapped[str] = mapped_column(String(10), default="manual")  # manual/seed/learned
    status: Mapped[str] = mapped_column(String(10), default="published")  # published/draft/disabled
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    source_candidate_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON 向量（语义检索）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class ManualDoc(Base):
    """产品手册文档（上传后解析切块）"""
    __tablename__ = "manual_docs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(200))
    file_type: Mapped[str] = mapped_column(String(10), default="txt")  # pdf/docx/txt/md
    status: Mapped[str] = mapped_column(String(10), default="ready")  # ready/failed
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ManualChunk(Base):
    """手册知识块（约500字/块，带章节出处）"""
    __tablename__ = "manual_chunks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_id: Mapped[int] = mapped_column(ForeignKey("manual_docs.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    section: Mapped[str] = mapped_column(String(200), default="")
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON 向量

    doc: Mapped["ManualDoc"] = relationship()


class TroubleshootingTree(Base):
    __tablename__ = "troubleshooting_trees"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_category: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(100))
    symptom_keywords: Mapped[str] = mapped_column(String(200), default="")  # 逗号分隔
    tree_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


# ---------- 满意度 ----------

class SatisfactionRating(Base):
    __tablename__ = "satisfaction_ratings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    score: Mapped[int] = mapped_column(Integer)  # 1-5
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


# ---------- 自我学习 ----------

class LearningCandidate(Base):
    __tablename__ = "learning_candidates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(10), default="faq")  # faq/kb_gap/hot_issue
    question: Mapped[str] = mapped_column(Text)
    suggested_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(20), default="其他")
    source_conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id"), nullable=True)
    frequency: Mapped[int] = mapped_column(Integer, default=1)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)  # pending/approved/rejected
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer: Mapped[str | None] = mapped_column(String(50), nullable=True)
    kb_entry_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Reminder(Base):
    """主动服务提醒（客户通知 / 内部任务）"""
    __tablename__ = "reminders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    audience: Mapped[str] = mapped_column(String(10), default="customer")  # customer/staff
    type: Mapped[str] = mapped_column(String(20))  # warranty_expiry/maintenance/rma_update/low_rating_followup
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text, default="")
    related_no: Mapped[str | None] = mapped_column(String(50), nullable=True)  # 关联单号
    dedup_key: Mapped[str] = mapped_column(String(120), unique=True)  # 防重复生成
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)  # pending/done
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trigger: Mapped[str] = mapped_column(String(10), default="manual")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    conversations_scanned: Mapped[int] = mapped_column(Integer, default=0)
    candidates_created: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(10), default="running")  # running/done/failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
