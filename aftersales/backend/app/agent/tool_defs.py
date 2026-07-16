"""Agent 工具的 JSON Schema 定义。

顺序固定（利于提示缓存前缀稳定）。customer_id 一律由服务端注入，不作为模型参数。
"""

TOOL_LABELS = {
    "search_knowledge_base": "查询知识库",
    "get_troubleshooting_tree": "获取故障排查方案",
    "query_orders": "查询订单",
    "check_return_policy": "核对退换货政策",
    "create_rma": "提交退换货申请",
    "query_rma": "查询退换货进度",
    "create_ticket": "创建工单",
    "update_ticket": "更新工单",
    "query_tickets": "查询工单",
    "record_satisfaction": "记录满意度评价",
    "escalate_to_human": "转接人工客服",
}

TOOLS = [
    {
        "name": "search_knowledge_base",
        "description": "检索售后知识库与产品手册。返回两部分：results（FAQ/政策条目）和 manual_excerpts（产品手册原文片段，含手册名与章节出处）。回答产品、政策类问题前应优先调用；基于手册片段回答时注明出处。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索关键词或客户问题"},
                "category": {"type": "string",
                             "enum": ["产品使用", "故障排查", "退换货政策", "保修条款", "物流", "其他"],
                             "description": "可选，限定知识分类"},
                "top_k": {"type": "integer", "description": "返回条数，默认3"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_troubleshooting_tree",
        "description": "按产品类目和故障症状获取故障排查决策树。拿到树后应按节点逐步引导客户排查，一次只问一个步骤，根据客户回答走到下一节点，直到得出结论。",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_category": {"type": "string", "description": "产品类目，如：扫地机器人、智能音箱、空气净化器、智能门锁、电动牙刷"},
                "symptom": {"type": "string", "description": "故障症状描述，如：不开机、连不上网"},
            },
            "required": ["product_category", "symptom"],
        },
    },
    {
        "name": "query_orders",
        "description": "查询当前客户的订单。不传参数返回最近订单摘要；传 order_no 返回订单详情（含保修截止日、退换货资格日期）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_no": {"type": "string", "description": "订单号，如 SO20260701-0003"},
                "keyword": {"type": "string", "description": "商品名称模糊搜索"},
            },
        },
    },
    {
        "name": "check_return_policy",
        "description": "核对某订单是否符合退货/换货/维修政策（按签收日期计算 7 天无理由退货、15 天换货、保修期维修）。发起退换货申请前必须先调用此工具。",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_no": {"type": "string", "description": "订单号"},
                "request_type": {"type": "string", "enum": ["退货", "换货", "维修"]},
            },
            "required": ["order_no", "request_type"],
        },
    },
    {
        "name": "create_rma",
        "description": "为客户订单发起退换货/维修申请（RMA）。调用前必须先用 check_return_policy 确认资格，并向客户确认。不符合政策时会返回失败原因。",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_no": {"type": "string", "description": "订单号"},
                "type": {"type": "string", "enum": ["退货", "换货", "维修"]},
                "reason": {"type": "string", "description": "申请原因"},
            },
            "required": ["order_no", "type", "reason"],
        },
    },
    {
        "name": "query_rma",
        "description": "查询当前客户的退换货申请。不传参数返回所有进行中的申请；传 rma_no 返回详情与处理流水。",
        "input_schema": {
            "type": "object",
            "properties": {
                "rma_no": {"type": "string", "description": "退换货单号，如 RMA20260710-0001"},
            },
        },
    },
    {
        "name": "create_ticket",
        "description": "创建售后工单，用于需要人工跟进的问题（复杂故障、投诉、物流异常等）。返回工单号。",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "工单标题"},
                "description": {"type": "string", "description": "问题详细描述（含已尝试的排查步骤）"},
                "category": {"type": "string",
                             "enum": ["故障报修", "物流咨询", "投诉建议", "退换货", "其他"]},
                "priority": {"type": "string", "enum": ["低", "中", "高", "紧急"]},
                "order_no": {"type": "string", "description": "关联订单号（可选）"},
            },
            "required": ["title", "description", "category", "priority"],
        },
    },
    {
        "name": "update_ticket",
        "description": "推进工单状态或补充备注。状态机：待处理→处理中→待客户确认→已解决→已关闭。客户确认问题已解决时把工单推到「已解决」。",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticket_no": {"type": "string", "description": "工单号"},
                "status": {"type": "string",
                           "enum": ["处理中", "待客户确认", "已解决", "已关闭"],
                           "description": "目标状态（可选）"},
                "note": {"type": "string", "description": "备注（可选）"},
            },
            "required": ["ticket_no"],
        },
    },
    {
        "name": "query_tickets",
        "description": "查询当前客户的工单。默认只返回未关闭工单；传 ticket_no 返回详情与流水。",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticket_no": {"type": "string", "description": "工单号"},
                "only_open": {"type": "boolean", "description": "仅未结工单，默认 true"},
            },
        },
    },
    {
        "name": "record_satisfaction",
        "description": "客户在对话中给出满意度评价（1-5星）时记录评分。",
        "input_schema": {
            "type": "object",
            "properties": {
                "score": {"type": "integer", "description": "1-5 分"},
                "comment": {"type": "string", "description": "评价内容（可选）"},
            },
            "required": ["score"],
        },
    },
    {
        "name": "escalate_to_human",
        "description": "转接人工客服。适用：客户明确要求人工、问题超出能力范围、投诉升级、多次尝试未解决。会自动创建高优先级工单并附上交接摘要。",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string",
                           "enum": ["客户要求", "超出能力", "投诉升级", "多次未解决"]},
                "summary": {"type": "string", "description": "问题交接摘要：客户诉求、已尝试的方案、当前进展"},
            },
            "required": ["reason", "summary"],
        },
    },
]
