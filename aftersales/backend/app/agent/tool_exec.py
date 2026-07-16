"""Agent 工具的真实业务实现。

所有工具在 ToolContext（db + 当前会话 + 当前客户）下执行，customer_id 由服务端注入。
返回值统一为 dict（JSON 序列化后回传给模型），失败时 ok=False + message。
"""
import json
from datetime import timedelta

from sqlalchemy.orm import Session

from ..models import (
    Conversation,
    Customer,
    Order,
    Product,
    RmaEvent,
    RmaRequest,
    SatisfactionRating,
    Ticket,
    TicketEvent,
    TroubleshootingTree,
)
from ..services import kb_search, manual_service, rma_service, ticket_service


class ToolContext:
    def __init__(self, db: Session, conversation: Conversation, customer: Customer):
        self.db = db
        self.conversation = conversation
        self.customer = customer


def run_tool(name: str, tool_input: dict, ctx: ToolContext) -> tuple[dict, bool]:
    """执行工具，返回 (result_dict, is_error)"""
    fn = _REGISTRY.get(name)
    if fn is None:
        return {"ok": False, "message": f"未知工具：{name}"}, True
    try:
        result = fn(tool_input or {}, ctx)
        return result, not result.get("ok", True)
    except Exception as e:  # 工具内部异常回传给模型，让其调整策略
        return {"ok": False, "message": f"工具执行出错：{e}"}, True


# ---------- 各工具实现 ----------

def _order_brief(o: Order) -> dict:
    return {
        "order_no": o.order_no, "product": o.product.name, "category": o.product.category,
        "quantity": o.quantity, "amount": o.amount, "status": o.status,
        "purchased_at": o.purchased_at.strftime("%Y-%m-%d"),
        "delivered_at": o.delivered_at.strftime("%Y-%m-%d") if o.delivered_at else None,
    }


def _order_detail(o: Order) -> dict:
    d = _order_brief(o)
    p = o.product
    if o.delivered_at:
        d["退货截止"] = (o.delivered_at + timedelta(days=p.return_days)).strftime("%Y-%m-%d")
        d["换货截止"] = (o.delivered_at + timedelta(days=p.exchange_days)).strftime("%Y-%m-%d")
        d["保修截止"] = (o.delivered_at + timedelta(days=p.warranty_months * 30)).strftime("%Y-%m-%d")
    return d


def search_knowledge_base(inp: dict, ctx: ToolContext) -> dict:
    query = inp.get("query", "")
    results = kb_search.search(
        ctx.db, query, category=inp.get("category"),
        top_k=int(inp.get("top_k") or 3), count_hit=True)
    manual_excerpts = manual_service.search(ctx.db, query, top_k=3)
    if not results and not manual_excerpts:
        return {"ok": True, "results": [], "manual_excerpts": [],
                "message": "知识库与产品手册中均未找到相关内容"}
    return {"ok": True, "results": results, "manual_excerpts": manual_excerpts,
            "usage_hint": "manual_excerpts 是产品手册原文片段，基于其回答时请注明出处（手册名+章节）"}


def get_troubleshooting_tree(inp: dict, ctx: ToolContext) -> dict:
    category = (inp.get("product_category") or "").strip()
    symptom = (inp.get("symptom") or "").strip()
    trees = ctx.db.query(TroubleshootingTree).all()
    best, best_score = None, 0
    for t in trees:
        score = 0
        if t.product_category in category or category in t.product_category:
            score += 2
        for kw in t.symptom_keywords.split(","):
            if kw and (kw in symptom or symptom in kw):
                score += 3
        if score > best_score:
            best, best_score = t, score
    if best is None or best_score < 2:
        return {"ok": True, "found": False,
                "message": "没有匹配的排查树，请基于知识库常识引导客户，必要时创建工单转人工"}
    return {"ok": True, "found": True, "title": best.title,
            "product_category": best.product_category,
            "tree": json.loads(best.tree_json),
            "usage": "从 root 节点开始，一次只向客户提出一个节点的问题，根据客户回答选择 options 中的下一节点，到达 conclusion 节点时给出结论"}


def query_orders(inp: dict, ctx: ToolContext) -> dict:
    q = ctx.db.query(Order).filter(Order.customer_id == ctx.customer.id)
    order_no = (inp.get("order_no") or "").strip()
    if order_no:
        o = q.filter(Order.order_no == order_no).first()
        if not o:
            return {"ok": False, "message": f"未找到您名下订单 {order_no}，请核对订单号"}
        return {"ok": True, "order": _order_detail(o)}
    keyword = (inp.get("keyword") or "").strip()
    if keyword:
        q = q.join(Product, Order.product_id == Product.id).filter(Product.name.like(f"%{keyword}%"))
    orders = q.order_by(Order.purchased_at.desc()).limit(5).all()
    if not orders:
        return {"ok": True, "orders": [], "message": "您名下暂无订单记录"}
    return {"ok": True, "orders": [_order_brief(o) for o in orders]}


def check_return_policy(inp: dict, ctx: ToolContext) -> dict:
    order_no = (inp.get("order_no") or "").strip()
    o = ctx.db.query(Order).filter(Order.customer_id == ctx.customer.id,
                                   Order.order_no == order_no).first()
    if not o:
        return {"ok": False, "message": f"未找到您名下订单 {order_no}"}
    result = rma_service.check_policy(o, inp.get("request_type", "退货"))
    return {"ok": True, "order_no": order_no, "product": o.product.name,
            "request_type": inp.get("request_type"), **result}


def create_rma(inp: dict, ctx: ToolContext) -> dict:
    order_no = (inp.get("order_no") or "").strip()
    rma_type = inp.get("type", "退货")
    o = ctx.db.query(Order).filter(Order.customer_id == ctx.customer.id,
                                   Order.order_no == order_no).first()
    if not o:
        return {"ok": False, "message": f"未找到您名下订单 {order_no}"}
    policy = rma_service.check_policy(o, rma_type)
    if not policy["eligible"]:
        return {"ok": False, "message": f"不符合{rma_type}政策：{policy['reason']}"}
    existing = ctx.db.query(RmaRequest).filter(
        RmaRequest.order_id == o.id,
        RmaRequest.status.notin_(["已完成", "已驳回", "已取消"])).first()
    if existing:
        return {"ok": False,
                "message": f"该订单已有进行中的售后申请 {existing.rma_no}（{existing.type}，{existing.status}），请勿重复提交"}
    rma = rma_service.create_rma(
        ctx.db, order=o, customer_id=ctx.customer.id, rma_type=rma_type,
        reason=inp.get("reason", ""), conversation_id=ctx.conversation.id)
    ctx.db.commit()
    return {"ok": True, "rma_no": rma.rma_no, "type": rma.type, "status": rma.status,
            "product": o.product.name,
            "refund_amount": rma.refund_amount,
            "message": f"{rma_type}申请已提交，单号 {rma.rma_no}，客服会在 24 小时内审核",
            "card": {"kind": "rma", "no": rma.rma_no, "title": f"{rma.type}申请 - {o.product.name}",
                     "status": rma.status}}


def query_rma(inp: dict, ctx: ToolContext) -> dict:
    q = ctx.db.query(RmaRequest).filter(RmaRequest.customer_id == ctx.customer.id)
    rma_no = (inp.get("rma_no") or "").strip()
    if rma_no:
        r = q.filter(RmaRequest.rma_no == rma_no).first()
        if not r:
            return {"ok": False, "message": f"未找到您名下的退换货单 {rma_no}"}
        events = ctx.db.query(RmaEvent).filter(RmaEvent.rma_id == r.id).order_by(RmaEvent.created_at).all()
        return {"ok": True, "rma": {
            "rma_no": r.rma_no, "type": r.type, "status": r.status, "reason": r.reason,
            "product": r.order.product.name, "refund_amount": r.refund_amount,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M"),
            "timeline": [{"time": e.created_at.strftime("%m-%d %H:%M"),
                          "status": e.to_status, "note": e.note} for e in events]}}
    rows = q.filter(RmaRequest.status.notin_(["已完成", "已驳回", "已取消"])) \
            .order_by(RmaRequest.created_at.desc()).all()
    if not rows:
        return {"ok": True, "rmas": [], "message": "您没有进行中的退换货申请"}
    return {"ok": True, "rmas": [
        {"rma_no": r.rma_no, "type": r.type, "status": r.status,
         "product": r.order.product.name,
         "created_at": r.created_at.strftime("%Y-%m-%d")} for r in rows]}


def create_ticket(inp: dict, ctx: ToolContext) -> dict:
    order_id = None
    order_no = (inp.get("order_no") or "").strip()
    if order_no:
        o = ctx.db.query(Order).filter(Order.customer_id == ctx.customer.id,
                                       Order.order_no == order_no).first()
        if o:
            order_id = o.id
    t = ticket_service.create_ticket(
        ctx.db, customer_id=ctx.customer.id, title=inp.get("title", "售后工单"),
        description=inp.get("description", ""), category=inp.get("category", "其他"),
        priority=inp.get("priority", "中"), conversation_id=ctx.conversation.id,
        order_id=order_id)
    ctx.db.commit()
    return {"ok": True, "ticket_no": t.ticket_no, "status": t.status,
            "message": f"工单已创建，单号 {t.ticket_no}，售后团队会尽快跟进",
            "card": {"kind": "ticket", "no": t.ticket_no, "title": t.title, "status": t.status}}


def update_ticket(inp: dict, ctx: ToolContext) -> dict:
    ticket_no = (inp.get("ticket_no") or "").strip()
    t = ctx.db.query(Ticket).filter(Ticket.customer_id == ctx.customer.id,
                                    Ticket.ticket_no == ticket_no).first()
    if not t:
        return {"ok": False, "message": f"未找到您名下工单 {ticket_no}"}
    status = inp.get("status")
    note = inp.get("note") or ""
    try:
        if status and status != t.status:
            ticket_service.transition(ctx.db, t, status, note=note or "AI助手推进", operator="AI助手")
        elif note:
            ticket_service.add_note(ctx.db, t, note, operator="AI助手")
        ctx.db.commit()
    except ticket_service.InvalidTransition as e:
        return {"ok": False, "message": str(e)}
    return {"ok": True, "ticket_no": t.ticket_no, "status": t.status,
            "message": f"工单 {t.ticket_no} 已更新，当前状态：{t.status}"}


def query_tickets(inp: dict, ctx: ToolContext) -> dict:
    q = ctx.db.query(Ticket).filter(Ticket.customer_id == ctx.customer.id)
    ticket_no = (inp.get("ticket_no") or "").strip()
    if ticket_no:
        t = q.filter(Ticket.ticket_no == ticket_no).first()
        if not t:
            return {"ok": False, "message": f"未找到您名下工单 {ticket_no}"}
        events = ctx.db.query(TicketEvent).filter(TicketEvent.ticket_id == t.id) \
            .order_by(TicketEvent.created_at).all()
        return {"ok": True, "ticket": {
            "ticket_no": t.ticket_no, "title": t.title, "status": t.status,
            "category": t.category, "priority": t.priority,
            "created_at": t.created_at.strftime("%Y-%m-%d %H:%M"),
            "timeline": [{"time": e.created_at.strftime("%m-%d %H:%M"),
                          "status": e.to_status, "note": e.note, "operator": e.operator}
                         for e in events]}}
    only_open = inp.get("only_open", True)
    if only_open:
        q = q.filter(Ticket.status != "已关闭")
    rows = q.order_by(Ticket.created_at.desc()).limit(10).all()
    if not rows:
        return {"ok": True, "tickets": [], "message": "您没有" + ("未结" if only_open else "") + "工单"}
    return {"ok": True, "tickets": [
        {"ticket_no": t.ticket_no, "title": t.title, "status": t.status,
         "priority": t.priority, "created_at": t.created_at.strftime("%Y-%m-%d")} for t in rows]}


def record_satisfaction(inp: dict, ctx: ToolContext) -> dict:
    score = max(1, min(5, int(inp.get("score", 5))))
    existing = ctx.db.query(SatisfactionRating).filter(
        SatisfactionRating.conversation_id == ctx.conversation.id).first()
    if existing:
        existing.score = score
        existing.comment = inp.get("comment")
    else:
        ctx.db.add(SatisfactionRating(
            conversation_id=ctx.conversation.id, customer_id=ctx.customer.id,
            score=score, comment=inp.get("comment")))
    ctx.db.commit()
    return {"ok": True, "score": score, "message": f"已记录您的 {score} 星评价，感谢反馈！"}


def escalate_to_human(inp: dict, ctx: ToolContext) -> dict:
    ctx.conversation.handed_off = True
    t = ticket_service.create_ticket(
        ctx.db, customer_id=ctx.customer.id,
        title=f"【转人工】{(inp.get('summary') or '客户问题')[:80]}",
        description=f"转人工原因：{inp.get('reason', '客户要求')}\n\n交接摘要：\n{inp.get('summary', '')}",
        category="其他", priority="高", conversation_id=ctx.conversation.id)
    ctx.db.commit()
    return {"ok": True, "ticket_no": t.ticket_no,
            "message": f"已为您转接人工客服并创建工单 {t.ticket_no}，工作时间（9:00-21:00）内预计 10 分钟响应",
            "card": {"kind": "ticket", "no": t.ticket_no, "title": t.title, "status": t.status}}


_REGISTRY = {
    "search_knowledge_base": search_knowledge_base,
    "get_troubleshooting_tree": get_troubleshooting_tree,
    "query_orders": query_orders,
    "check_return_policy": check_return_policy,
    "create_rma": create_rma,
    "query_rma": query_rma,
    "create_ticket": create_ticket,
    "update_ticket": update_ticket,
    "query_tickets": query_tickets,
    "record_satisfaction": record_satisfaction,
    "escalate_to_human": escalate_to_human,
}
