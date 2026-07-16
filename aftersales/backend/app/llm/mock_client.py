"""演示模式 LLM：规则引擎模拟 Claude 的多轮工具调用行为。

原则：只模拟"模型决策"，工具执行/数据库/状态机全部走真实代码路径。
stop_reason 语义与真实 API 一致（要调工具时为 tool_use，收尾为 end_turn），
engine 的循环逻辑因此被完整复用。
"""
import asyncio
import json
import re
import uuid
from typing import AsyncIterator

from .base import AnalysisResult, LLMEvent, TextDelta, ToolUseStart, TurnEnd

CHUNK = 12          # 打字机切块字数
TYPE_DELAY = 0.02   # 每块延迟
THINK_DELAY = 0.25  # 工具调用前思考延迟


def _tid() -> str:
    return "toolu_mock_" + uuid.uuid4().hex[:12]


def _extract(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text or "", re.I)
    return m.group(1).upper() if m else None


class MockClient:
    """规则版 LLM。会话内多步状态（排查树游标、待确认RMA）由 engine 传入 mock_state 持久化。"""

    # ---------- 聊天 ----------

    async def stream_turn(self, system: str, messages: list[dict],
                          tools: list[dict], *, mock_state: dict | None = None
                          ) -> AsyncIterator[LLMEvent]:
        state = mock_state if mock_state is not None else {}
        last_user_text = _last_user_text(messages)
        tool_results = _last_tool_results(messages)

        if tool_results:
            # 上一轮发出的工具调用已返回 → 基于结果生成回复（或下一步工具）
            async for ev in self._after_tools(state, tool_results):
                yield ev
        else:
            # 新的用户消息 → 意图识别
            async for ev in self._on_user_message(state, last_user_text):
                yield ev

    # ---------- 意图识别 ----------

    async def _on_user_message(self, state: dict, text: str) -> AsyncIterator[LLMEvent]:
        t = text or ""

        # 进行中的排查树：用户在回答排查问题
        if state.get("tree_node") and state.get("tree"):
            async for ev in self._tree_step(state, t):
                yield ev
            return

        # 待确认的 RMA：用户回复确认/否认
        if state.get("pending_rma"):
            if re.search(r"确认|是的|好的|可以|要退|申请吧|嗯|OK|ok|同意", t):
                p = state.pop("pending_rma")
                async for ev in self._emit_tools(
                    "好的，正在为您提交申请…",
                    [("create_rma", {"order_no": p["order_no"], "type": p["type"],
                                     "reason": p.get("reason", "客户申请")})],
                    state, phase="rma_created"):
                    yield ev
                return
            if re.search(r"不用|算了|取消|不了|再想想", t):
                state.pop("pending_rma", None)
                async for ev in self._say("好的，已为您取消本次申请。还有什么可以帮您？"):
                    yield ev
                return

        # 满意度评分（含数字或星）
        m = re.search(r"([1-5])\s*(分|星)", t)
        if m or re.search(r"^(非常满意|满意|很好|好评)$", t.strip()):
            score = int(m.group(1)) if m else 5
            async for ev in self._emit_tools(
                "收到您的评价，正在记录…",
                [("record_satisfaction", {"score": score, "comment": t.strip()})],
                state, phase="satisfaction"):
                yield ev
            return

        # 转人工/投诉
        if re.search(r"人工|真人|客服电话|投诉|太差|气死|生气|什么破|垃圾", t):
            async for ev in self._emit_tools(
                "非常抱歉给您带来不好的体验，正在为您转接人工客服…",
                [("escalate_to_human", {"reason": "客户要求",
                                        "summary": f"客户诉求：{t[:100]}。请人工客服尽快跟进。"})],
                state, phase="escalated"):
                yield ev
            return

        # 查退换货进度
        rma_no = _extract(r"(RMA\d{8}-\d{4})", t)
        if rma_no or re.search(r"(退货|换货|维修|售后).{0,6}(进度|状态|到哪|怎么样了)", t):
            async for ev in self._emit_tools(
                "正在为您查询退换货进度…",
                [("query_rma", {"rma_no": rma_no} if rma_no else {})],
                state, phase="rma_queried"):
                yield ev
            return

        # 查工单
        ticket_no = _extract(r"(TK\d{8}-\d{4})", t)
        if ticket_no or re.search(r"工单.{0,6}(进度|状态|怎么样)", t):
            async for ev in self._emit_tools(
                "正在为您查询工单…",
                [("query_tickets", {"ticket_no": ticket_no} if ticket_no else {"only_open": True})],
                state, phase="ticket_queried"):
                yield ev
            return

        # 有未完成的退换货意图（如排查树结论后等客户报订单号）
        if state.get("rma_intent"):
            order_no = _extract(r"(SO\d{8}-\d{4})", t)
            if order_no:
                intent = state["rma_intent"]
                intent["order_no"] = order_no
                async for ev in self._emit_tools(
                    f"好的，正在核实该订单的{intent['type']}资格…",
                    [("query_orders", {"order_no": order_no}),
                     ("check_return_policy", {"order_no": order_no, "request_type": intent["type"]})],
                    state, phase="policy_checked"):
                    yield ev
                return

        # 退换货意图
        rma_type = "退货" if re.search(r"退货|退款|不想要|退了", t) else \
                   "换货" if re.search(r"换货|换一台|换个新的", t) else \
                   "维修" if re.search(r"维修|修一下|保修|修理", t) else None
        if rma_type:
            order_no = _extract(r"(SO\d{8}-\d{4})", t)
            state["rma_intent"] = {"type": rma_type, "reason": t[:100], "order_no": order_no}
            if order_no:
                async for ev in self._emit_tools(
                    f"好的，正在核实订单与{rma_type}政策…",
                    [("query_orders", {"order_no": order_no}),
                     ("check_return_policy", {"order_no": order_no, "request_type": rma_type})],
                    state, phase="policy_checked"):
                    yield ev
            else:
                async for ev in self._emit_tools(
                    "好的，先帮您调取名下订单…",
                    [("query_orders", {})], state, phase="orders_for_rma"):
                    yield ev
            return

        # 查订单
        order_no = _extract(r"(SO\d{8}-\d{4})", t)
        if order_no or re.search(r"订单|我买的|物流|发货|快递|到哪了", t):
            async for ev in self._emit_tools(
                "正在查询您的订单…",
                [("query_orders", {"order_no": order_no} if order_no else {})],
                state, phase="orders_listed"):
                yield ev
            return

        # 故障排查意图
        if re.search(r"不开机|开不了机|没反应|不工作|连不上|无法连接|配不上网|不出声|没声音|异味|失灵|故障|坏了|充不进|不转", t):
            category = _guess_category(t)
            state["fault_desc"] = t[:100]
            async for ev in self._emit_tools(
                "了解，我来帮您排查。正在调取相关故障的排查方案…",
                [("search_knowledge_base", {"query": t, "top_k": 3}),
                 ("get_troubleshooting_tree", {"product_category": category, "symptom": t[:50]})],
                state, phase="tree_loaded"):
                yield ev
            return

        # 问候
        if re.search(r"^(你好|您好|hi|hello|在吗|嗨)[!！。~？?\s]*$", t.strip(), re.I):
            async for ev in self._say(
                "您好！我是智服小助，很高兴为您服务 😊\n\n我可以帮您：\n"
                "· 查询订单与物流\n· 产品故障排查\n· 办理退换货/保修维修\n· 查询工单与售后进度\n\n请问有什么可以帮您？"):
                yield ev
            return

        # 兜底：检索知识库
        async for ev in self._emit_tools(
            "正在为您查询相关资料…",
            [("search_knowledge_base", {"query": t, "top_k": 3})],
            state, phase="kb_answer"):
            yield ev

    # ---------- 工具结果后处理 ----------

    async def _after_tools(self, state: dict, results: list[dict]) -> AsyncIterator[LLMEvent]:
        phase = state.pop("phase", "")
        data = {r["name"]: r["result"] for r in results}

        if phase == "kb_answer":
            kb = data.get("search_knowledge_base", {})
            hits = kb.get("results") or []
            manual_hits = kb.get("manual_excerpts") or []
            if hits:
                top = hits[0]
                text = f"{top['answer']}\n\n以上信息来自知识库「{top['title']}」。如果没有解决您的问题，我可以为您转接人工客服。"
            elif manual_hits:
                top = manual_hits[0]
                src = f"《{top['doc']}》" + (f"·{top['section']}" if top.get("section") else "")
                text = (f"根据产品手册 {src}：\n\n{top['content']}\n\n"
                        f"如果没有解决您的问题，我可以为您转接人工客服。")
            else:
                text = ("抱歉，这个问题我暂时没有在知识库和产品手册中找到确切答案。您可以换个说法再问一次，"
                        "或者我帮您转接人工客服/创建工单跟进，需要吗？")
            async for ev in self._say(text):
                yield ev
            return

        if phase == "orders_listed":
            q = data.get("query_orders", {})
            if "order" in q:
                o = q["order"]
                lines = [f"为您找到订单 {o['order_no']}：",
                         f"· 商品：{o['product']} ×{o['quantity']}",
                         f"· 金额：¥{o['amount']}",
                         f"· 状态：{o['status']}",
                         f"· 下单：{o['purchased_at']}" + (f"，签收：{o['delivered_at']}" if o.get('delivered_at') else "")]
                if o.get("退货截止"):
                    lines.append(f"· 退货截止 {o['退货截止']} / 换货截止 {o['换货截止']} / 保修至 {o['保修截止']}")
                lines.append("\n需要为这笔订单办理售后吗？")
                text = "\n".join(lines)
            elif q.get("orders"):
                lines = ["为您找到以下订单："]
                for o in q["orders"]:
                    lines.append(f"· {o['order_no']} | {o['product']} | ¥{o['amount']} | {o['status']}")
                lines.append("\n回复订单号可查看详情或办理售后。")
                text = "\n".join(lines)
            else:
                text = q.get("message", "您名下暂无订单。")
            async for ev in self._say(text):
                yield ev
            return

        if phase == "orders_for_rma":
            q = data.get("query_orders", {})
            intent = state.get("rma_intent", {})
            if q.get("orders"):
                lines = [f"好的，您想办理**{intent.get('type', '售后')}**。您名下的订单如下："]
                for o in q["orders"]:
                    lines.append(f"· {o['order_no']} | {o['product']} | {o['status']}" +
                                 (f" | 签收 {o['delivered_at']}" if o.get("delivered_at") else ""))
                lines.append("\n请告诉我要办理的**订单号**（如 " + q["orders"][0]["order_no"] + "）。")
                text = "\n".join(lines)
            else:
                text = "您名下暂无订单，无法办理售后。如有疑问可转人工客服核实。"
            async for ev in self._say(text):
                yield ev
            return

        if phase == "policy_checked":
            pol = data.get("check_return_policy", {})
            intent = state.pop("rma_intent", {})
            if pol.get("eligible"):
                state["pending_rma"] = {"order_no": pol.get("order_no"),
                                        "type": intent.get("type", pol.get("request_type", "退货")),
                                        "reason": intent.get("reason", "")}
                text = (f"已为您核实：{pol.get('product', '')} 订单 {pol.get('order_no')}\n"
                        f"✅ {pol.get('reason', '符合政策')}\n\n"
                        f"确认要提交{state['pending_rma']['type']}申请吗？（回复\"确认\"提交）")
            else:
                alt = ""
                if intent.get("type") == "退货":
                    alt = "\n\n您可以考虑：若在换货期内可申请**换货**，保修期内可申请**免费维修**。需要我帮您核实吗？"
                text = (f"很抱歉，经核实该订单暂不符合{intent.get('type', '退货')}条件：\n"
                        f"❌ {pol.get('reason', pol.get('message', '不符合政策'))}{alt}\n\n"
                        f"如有特殊情况，我也可以为您转接人工客服协商处理。")
            async for ev in self._say(text):
                yield ev
            return

        if phase == "rma_created":
            r = data.get("create_rma", {})
            if r.get("ok"):
                text = (f"✅ {r.get('message')}\n\n"
                        f"后续流程：审核通过 → 按指引寄回商品 → 验收后{('退款到原支付账户' if r.get('type') == '退货' else '为您安排' + str(r.get('type')))}。"
                        f"您可以随时发送单号 {r.get('rma_no')} 查询进度。\n\n还有其他需要帮助的吗？")
            else:
                text = f"申请提交失败：{r.get('message', '未知原因')}。需要我帮您转人工处理吗？"
            async for ev in self._say(text):
                yield ev
            return

        if phase == "rma_queried":
            r = data.get("query_rma", {})
            if r.get("rma"):
                d = r["rma"]
                lines = [f"退换货单 {d['rma_no']}（{d['type']}）当前状态：**{d['status']}**",
                         f"商品：{d['product']}"]
                if d.get("timeline"):
                    lines.append("\n处理进度：")
                    for e in d["timeline"]:
                        lines.append(f"· {e['time']} {e['status']}" + (f"（{e['note']}）" if e.get("note") else ""))
                text = "\n".join(lines)
            elif r.get("rmas"):
                lines = ["您进行中的售后申请："]
                for d in r["rmas"]:
                    lines.append(f"· {d['rma_no']} | {d['type']} | {d['product']} | {d['status']}")
                text = "\n".join(lines)
            else:
                text = r.get("message", "您没有进行中的退换货申请。")
            async for ev in self._say(text):
                yield ev
            return

        if phase == "ticket_queried":
            r = data.get("query_tickets", {})
            if r.get("ticket"):
                d = r["ticket"]
                lines = [f"工单 {d['ticket_no']}：{d['title']}",
                         f"状态：**{d['status']}** | 优先级：{d['priority']}"]
                if d.get("timeline"):
                    lines.append("\n处理记录：")
                    for e in d["timeline"][-4:]:
                        lines.append(f"· {e['time']} [{e['operator']}] {e['status']}" +
                                     (f"：{e['note']}" if e.get("note") else ""))
                text = "\n".join(lines)
            elif r.get("tickets"):
                lines = ["您的未结工单："]
                for d in r["tickets"]:
                    lines.append(f"· {d['ticket_no']} | {d['title']} | {d['status']}")
                text = "\n".join(lines)
            else:
                text = r.get("message", "您没有未结工单。")
            async for ev in self._say(text):
                yield ev
            return

        if phase == "tree_loaded":
            tree_res = data.get("get_troubleshooting_tree", {})
            kb = data.get("search_knowledge_base", {})
            if tree_res.get("found"):
                tree = tree_res["tree"]
                state["tree"] = tree
                state["tree_node"] = tree.get("root")
                node = tree["nodes"][tree["root"]]
                opts = " / ".join(node.get("options", {}).keys())
                text = (f"我找到了「{tree_res.get('title')}」的排查方案，我们一步步来：\n\n"
                        f"**第一步**：{node['ask']}\n（请回复：{opts}）")
            elif kb.get("results"):
                top = kb["results"][0]
                text = f"{top['answer']}\n\n如果按上面操作仍未解决，请告诉我，我再帮您深入排查或转人工。"
            else:
                text = "我暂时没有找到这个故障的标准排查方案。建议我直接为您创建工单，由技术专员跟进，可以吗？"
            async for ev in self._say(text):
                yield ev
            return

        if phase == "escalated":
            r = data.get("escalate_to_human", {})
            text = (f"{r.get('message', '已为您转接人工客服。')}\n\n"
                    f"人工客服接入前，您也可以继续向我描述问题，我会同步记录到工单，帮助客服更快了解情况。")
            async for ev in self._say(text):
                yield ev
            return

        if phase == "satisfaction":
            r = data.get("record_satisfaction", {})
            score = r.get("score", 5)
            text = ("谢谢您的认可！能为您解决问题是我的荣幸 😊 祝您生活愉快！"
                    if score >= 4 else
                    "感谢您的反馈，很抱歉这次服务没有让您完全满意。我们会认真改进，您反馈的问题也已记录。")
            async for ev in self._say(text):
                yield ev
            return

        if phase == "tree_rma":
            # 排查树结论触发的维修政策核实
            pol = data.get("check_return_policy", {})
            if pol.get("eligible"):
                state["pending_rma"] = {"order_no": pol.get("order_no"), "type": "维修",
                                        "reason": state.get("fault_desc", "故障维修")}
                text = (f"✅ {pol.get('reason', '在保修期内')}\n\n"
                        f"确认为订单 {pol.get('order_no')} 提交**保修维修**申请吗？（回复\"确认\"提交）")
            else:
                text = (f"经核实：{pol.get('reason', pol.get('message', '不在保修期内'))}\n"
                        f"您可以选择付费维修，需要我创建工单让技术专员联系您报价吗？也可以转人工客服。")
            async for ev in self._say(text):
                yield ev
            return

        # 未知 phase 兜底
        async for ev in self._say("好的，已为您处理完成。还有什么可以帮您？"):
            yield ev

    # ---------- 排查树逐步引导 ----------

    async def _tree_step(self, state: dict, answer: str) -> AsyncIterator[LLMEvent]:
        tree = state["tree"]
        node_id = state["tree_node"]
        node = tree["nodes"].get(node_id, {})
        options: dict = node.get("options", {})

        ans = answer.strip()
        nxt = None
        # 1) 选项精确匹配
        for opt, target in options.items():
            if ans == opt or ans in opt.split("/"):
                nxt = target
                break
        # 2) 包含匹配：长选项优先（先“不亮”后“亮”，避免否定词被短选项抢占）
        if nxt is None:
            for opt, target in sorted(options.items(), key=lambda kv: -len(kv[0])):
                if opt in ans:
                    nxt = target
                    break
        # 3) 语义兜底：否定判断必须在肯定之前（“还是不亮”含“是”也含“不”）
        if nxt is None and options:
            if re.search(r"不|没|否|仍|依旧|失败|无", ans):
                nxt = list(options.values())[-1]
            elif re.search(r"是|对|亮|有|好了|可以|正常|成功|嗯", ans):
                nxt = list(options.values())[0]

        if nxt is None:
            opts = " / ".join(options.keys())
            async for ev in self._say(f"抱歉我没太理解您的意思。{node.get('ask', '')}\n（请回复：{opts}）"):
                yield ev
            return

        next_node = tree["nodes"].get(nxt, {})
        if "conclusion" in next_node:
            state.pop("tree", None)
            state.pop("tree_node", None)
            conclusion = next_node["conclusion"]
            action = next_node.get("action", "")
            if action == "create_rma_repair":
                # 结论指向保修维修 → 查订单核实保修
                order_no = state.get("rma_order_no")
                if order_no:
                    async for ev in self._emit_tools(
                        f"排查结论：{conclusion}\n\n正在为您核实保修资格…",
                        [("check_return_policy", {"order_no": order_no, "request_type": "维修"})],
                        state, phase="tree_rma"):
                        yield ev
                else:
                    async for ev in self._emit_tools(
                        f"排查结论：{conclusion}\n\n我先调取您的订单，为您核实保修资格…",
                        [("query_orders", {})], state, phase="orders_for_rma"):
                        yield ev
                    state["rma_intent"] = {"type": "维修", "reason": state.get("fault_desc", "故障维修")}
                return
            if action == "resolved":
                async for ev in self._say(
                    f"太好了！{conclusion}\n\n如果后续再遇到问题随时找我。方便的话，给本次服务打个分吧（1-5星）😊"):
                    yield ev
                return
            async for ev in self._say(f"排查结论：{conclusion}\n\n需要我为您创建工单跟进，或转人工客服吗？"):
                yield ev
            return

        state["tree_node"] = nxt
        opts = " / ".join(next_node.get("options", {}).keys())
        async for ev in self._say(f"**下一步**：{next_node.get('ask', '')}\n（请回复：{opts}）"):
            yield ev

    # ---------- 基础产出 ----------

    async def _say(self, text: str) -> AsyncIterator[LLMEvent]:
        for i in range(0, len(text), CHUNK):
            yield TextDelta(text[i:i + CHUNK])
            await asyncio.sleep(TYPE_DELAY)
        yield TurnEnd(stop_reason="end_turn",
                      content_blocks=[{"type": "text", "text": text}],
                      usage_in=0, usage_out=len(text))

    async def _emit_tools(self, lead_text: str, calls: list[tuple[str, dict]],
                          state: dict, phase: str) -> AsyncIterator[LLMEvent]:
        """先说一句引导语，再发出 tool_use（多个则并行），交回 engine 执行"""
        state["phase"] = phase
        for i in range(0, len(lead_text), CHUNK):
            yield TextDelta(lead_text[i:i + CHUNK])
            await asyncio.sleep(TYPE_DELAY)
        await asyncio.sleep(THINK_DELAY)
        blocks: list = [{"type": "text", "text": lead_text}]
        for name, tool_input in calls:
            tool_id = _tid()
            yield ToolUseStart(id=tool_id, name=name)
            blocks.append({"type": "tool_use", "id": tool_id, "name": name, "input": tool_input})
        yield TurnEnd(stop_reason="tool_use", content_blocks=blocks,
                      usage_in=0, usage_out=len(lead_text))

    # ---------- 视觉/OCR/质检（规则版占位，真实API模式效果完整） ----------

    def analyze_image(self, image_b64: str, mime: str, hint: str = "") -> str:
        return ("（演示模式：图像识别需要真实 API）已收到您上传的照片。"
                "请再用文字补充描述故障现象，如指示灯状态、错误提示内容等，我来帮您排查。")

    def ocr_image(self, image_b64: str, mime: str = "image/png") -> str:
        return ""

    def qa_review(self, transcript: str) -> dict:
        polite = 90 if re.search(r"您好|抱歉|感谢", transcript) else 70
        resolved = 85 if not re.search(r"转接人工|未找到|无法解决", transcript) else 65
        score = int(polite * 0.3 + 80 * 0.3 + resolved * 0.4)
        return {"score": score,
                "dimensions": {"服务态度": polite, "专业准确": 80, "解决效率": resolved},
                "issues": [] if score >= 80 else ["会话中出现未解决/转人工信号，建议复盘"],
                "suggestion": "演示模式为规则评分，接入真实 API 可获得深度质检分析"}

    # ---------- 人工工作台推荐话术（规则版） ----------

    def suggest_reply(self, transcript: str) -> str:
        last_user = ""
        for line in reversed(transcript.split("\n")):
            if line.startswith("客户:"):
                last_user = line[3:].strip()
                break
        if re.search(r"投诉|生气|太差|气死", transcript):
            return ("非常抱歉给您带来了不好的体验，我完全理解您的心情。您反馈的问题我已详细记录并加急处理，"
                    "我们会在今天内给您明确答复，处理结果第一时间同步您。")
        if last_user:
            return (f"您好，关于您提到的「{last_user[:30]}」，我来为您跟进处理。"
                    "请您稍等，我核实后马上给您准确答复；如有补充信息也可以直接发给我。")
        return "您好，我是人工客服，很高兴为您服务。请问还有什么可以帮您？"

    # ---------- 手册消化（规则版：按章节生成占位候选，真实API模式效果更佳） ----------

    def digest_manual(self, title: str, manual_text: str) -> list[dict]:
        out = []
        for m in re.finditer(r"【(.+?)】\n(.+?)(?=\n\n【|\Z)", manual_text, re.S):
            section, body = m.group(1).strip(), m.group(2).strip()
            if len(body) < 30 or len(out) >= 8:
                continue
            out.append({"question": f"{title}：{section}怎么操作/有什么要求？",
                        "suggested_answer": body[:300],
                        "category": "产品使用", "confidence": 0.4})
        return out

    # ---------- 离线学习分析（规则版） ----------

    def analyze_conversation(self, transcript: str) -> AnalysisResult:
        lines = [l for l in transcript.split("\n") if l.strip()]
        user_lines = [l[3:].strip() for l in lines if l.startswith("客户:")]
        ai_lines = [l[3:].strip() for l in lines if l.startswith("客服:")]

        first_q = user_lines[0] if user_lines else "（无客户提问）"
        # 选最长的实质性 AI 回复作为候选答案（排除客套话与转人工话术）
        substantial = [l for l in ai_lines
                       if len(l) > 30 and "转接人工" not in l
                       and not re.match(r"^(不客气|太好了|感谢|谢谢|好的|收到)", l)]
        answer = max(substantial, key=len) if substantial else ""

        bad_signals = re.search(r"转接人工|没有.{0,4}找到|未找到|无法解决|投诉|很抱歉.{0,10}(没有|无法)", transcript)
        resolved = not bad_signals

        tags = []
        for cat, kws in _TAG_RULES.items():
            for kw in kws:
                if kw in transcript:
                    tags.append(cat)
                    break
        tags = tags[:3] or ["综合咨询"]

        faq, gaps = [], []
        if resolved and answer and len(first_q) >= 4:
            faq.append({"question": first_q, "suggested_answer": answer, "confidence": 0.6})
        if not resolved and len(first_q) >= 4:
            gaps.append({"question": first_q,
                         "context": "会话中出现转人工/未解决/知识库未命中信号，建议补充知识"})

        return AnalysisResult(
            resolved=resolved,
            summary=f"客户咨询：{first_q[:50]}。" + ("已解决" if resolved else "未完全解决（转人工/知识缺口）"),
            category=_guess_kb_category(transcript),
            faq_candidates=faq, kb_gaps=gaps, issue_tags=tags)


_TAG_RULES = {
    "扫地机器人-故障": ["扫地机", "不回充", "吸力"],
    "智能音箱-故障": ["音箱", "没声音", "不出声"],
    "空气净化器-故障": ["净化器", "异味", "滤芯"],
    "智能门锁-故障": ["门锁", "指纹"],
    "配网问题": ["连不上", "无法连接", "配网", "WiFi", "wifi"],
    "开机问题": ["不开机", "开不了机", "没反应"],
    "退货咨询": ["退货", "退款"],
    "换货咨询": ["换货"],
    "保修维修": ["维修", "保修"],
    "物流咨询": ["物流", "快递", "发货"],
}


def _guess_category(text: str) -> str:
    for cat in ["扫地机器人", "智能音箱", "空气净化器", "智能门锁", "电动牙刷"]:
        if cat in text or cat[:3] in text:
            return cat
    if re.search(r"扫地|吸尘", text):
        return "扫地机器人"
    if re.search(r"音箱|音响", text):
        return "智能音箱"
    if re.search(r"净化|滤芯", text):
        return "空气净化器"
    if re.search(r"门锁|指纹", text):
        return "智能门锁"
    if re.search(r"牙刷", text):
        return "电动牙刷"
    return "通用"


def _guess_kb_category(text: str) -> str:
    if re.search(r"退货|换货|退款", text):
        return "退换货政策"
    if re.search(r"保修|维修", text):
        return "保修条款"
    if re.search(r"物流|快递|发货", text):
        return "物流"
    if re.search(r"不开机|故障|没反应|连不上|异味|失灵", text):
        return "故障排查"
    return "产品使用"


def _last_user_text(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m.get("role") != "user":
            continue
        content = m.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
            if texts:
                return "\n".join(texts)
            # 全是 tool_result 的 user 消息不算用户输入
            continue
    return ""


def _last_tool_results(messages: list[dict]) -> list[dict]:
    """若最后一条 user 消息是 tool_result 集合，解析出 [{name,result}]（name 从上一条 assistant 的 tool_use 对应）"""
    if not messages:
        return []
    last = messages[-1]
    if last.get("role") != "user" or not isinstance(last.get("content"), list):
        return []
    results = [b for b in last["content"] if isinstance(b, dict) and b.get("type") == "tool_result"]
    if not results:
        return []
    # 建立 tool_use_id -> name 映射
    id2name = {}
    for m in reversed(messages[:-1]):
        if m.get("role") == "assistant" and isinstance(m.get("content"), list):
            for b in m["content"]:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    id2name[b["id"]] = b["name"]
            break
    out = []
    for r in results:
        raw = r.get("content", "")
        if isinstance(raw, list):
            raw = "".join(b.get("text", "") for b in raw if isinstance(b, dict))
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            parsed = {"message": str(raw)}
        out.append({"name": id2name.get(r.get("tool_use_id"), ""), "result": parsed})
    return out
