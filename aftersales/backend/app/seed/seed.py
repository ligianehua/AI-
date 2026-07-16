"""演示种子数据（幂等：已有数据则跳过）。

订单签收日期按“距今天数”动态生成，保证退货/换货/保修政策边界随时可演示。
"""
import json
from datetime import datetime, timedelta

from ..database import SessionLocal, init_db
from ..models import (
    AnalysisRun,
    Conversation,
    Customer,
    KbEntry,
    LearningCandidate,
    Message,
    Order,
    Product,
    RmaEvent,
    RmaRequest,
    SatisfactionRating,
    Ticket,
    TicketEvent,
    TroubleshootingTree,
)
from ..services import kb_search


def _days_ago(n: int, hour: int = 10) -> datetime:
    return (datetime.now() - timedelta(days=n)).replace(hour=hour, minute=30, second=0, microsecond=0)


PRODUCTS = [
    dict(name="智能音箱 X1", model_no="X1-2025", category="智能音箱", price=399, warranty_months=12),
    dict(name="扫地机器人 S7", model_no="S7-Pro", category="扫地机器人", price=2499, warranty_months=24),
    dict(name="空气净化器 A3", model_no="A3-Max", category="空气净化器", price=1299, warranty_months=12),
    dict(name="智能门锁 L2", model_no="L2-Plus", category="智能门锁", price=1599, warranty_months=24),
    dict(name="电动牙刷 T5", model_no="T5-Mini", category="电动牙刷", price=299, warranty_months=12),
]

CUSTOMERS = [
    dict(name="张伟", phone="13800000001", email="zhangwei@example.com", level="VIP"),
    dict(name="李娜", phone="13800000002", email="lina@example.com", level="普通"),
    dict(name="王芳", phone="13800000003", email="wangfang@example.com", level="SVIP"),
    dict(name="刘强", phone="13800000004", email="liuqiang@example.com", level="普通"),
    dict(name="陈静", phone="13800000005", email="chenjing@example.com", level="VIP"),
    dict(name="杨洋", phone="13800000006", email="yangyang@example.com", level="普通"),
    dict(name="赵敏", phone="13800000007", email="zhaomin@example.com", level="普通"),
    dict(name="孙磊", phone="13800000008", email="sunlei@example.com", level="VIP"),
]

# (customer_idx, product_idx, delivered_days_ago 或 None=在途, 状态)
ORDERS = [
    # 张伟：覆盖全部政策边界（演示主账号）
    (0, 1, 3, "已签收"),      # 扫地机 S7，可退可换
    (0, 0, 10, "已签收"),     # 音箱 X1，仅换/修
    (0, 2, 90, "已完成"),     # 净化器 A3，保修内
    (0, 4, 500, "已完成"),    # 牙刷 T5，已过保
    (0, 3, None, "已发货"),   # 门锁 L2，在途
    # 李娜
    (1, 0, 5, "已签收"),
    (1, 1, 60, "已完成"),
    (1, 2, 420, "已完成"),    # 12月保修，已过保
    # 王芳
    (2, 3, 8, "已签收"),
    (2, 1, 180, "已完成"),
    (2, 4, 2, "已签收"),
    # 刘强
    (3, 2, 12, "已签收"),
    (3, 0, 240, "已完成"),
    # 陈静
    (4, 1, 14, "已签收"),
    (4, 3, 300, "已完成"),
    # 杨洋
    (5, 0, 30, "已完成"),
    (5, 4, 400, "已完成"),    # 已过保
    # 赵敏
    (6, 2, 120, "已完成"),
    (6, 1, None, "已付款"),   # 未发货
    # 孙磊
    (7, 0, 350, "已完成"),
]

KB_ENTRIES = [
    # 产品使用
    ("智能音箱 X1 如何配网", "智能音箱怎么连接WiFi？如何配网？",
     "1. 长按音箱顶部电源键 5 秒，指示灯闪烁进入配网模式；2. 打开「智家APP」→ 添加设备 → 选择智能音箱 X1；3. 按提示输入家中 2.4GHz WiFi 密码（暂不支持 5GHz）；4. 等待提示音「连接成功」即可。", "产品使用", "音箱,配网,WiFi"),
    ("扫地机器人 S7 如何绑定APP", "扫地机器人怎么绑定手机APP？",
     "打开「智家APP」→ 添加设备 → 扫地机器人 S7，同时按住主机「电源」和「回充」键 3 秒直到语音提示进入配对模式，按 APP 指引完成绑定。注意路由器需开启 2.4GHz 频段。", "产品使用", "扫地机,绑定,APP"),
    ("空气净化器 A3 滤芯更换教程", "空气净化器滤芯怎么换？多久换一次？",
     "滤芯建议每 6-12 个月更换一次（APP 会有滤芯寿命提醒）。更换步骤：断电 → 打开背部滤芯仓盖 → 逆时针旋出旧滤芯 → 撕掉新滤芯塑封后装入 → 长按机身「滤芯重置」键 5 秒完成重置。", "产品使用", "净化器,滤芯"),
    ("智能门锁 L2 添加指纹", "智能门锁怎么添加新指纹？",
     "管理员在门锁内侧按「设置」键 → 输入管理密码 → 选择「指纹管理-添加指纹」→ 按提示将手指在感应区反复按压 6 次直至提示成功。每把锁最多录入 50 枚指纹。", "产品使用", "门锁,指纹"),
    ("电动牙刷 T5 充电说明", "电动牙刷怎么充电？充一次用多久？",
     "使用附带的磁吸充电底座，充满约需 4 小时，指示灯常亮表示充满。充满一次以每天刷牙 2 次、每次 2 分钟计算可使用约 30 天。长期不用建议每 3 个月补电一次。", "产品使用", "牙刷,充电"),
    ("智能音箱 X1 语音唤醒设置", "音箱怎么换唤醒词？",
     "在「智家APP」→ 设备设置 → 唤醒词，可选「小智小智」或「智能管家」两种唤醒词。暂不支持自定义唤醒词。", "产品使用", "音箱,唤醒词"),
    ("扫地机器人 S7 划区清扫", "扫地机器人怎么设置只扫某个房间？",
     "APP 地图页 → 「划区清扫」→ 在地图上框选目标区域 → 点击「开始」。也可以在地图编辑中给房间命名后，直接语音「打扫客厅」。", "产品使用", "扫地机,划区"),
    ("空气净化器 A3 睡眠模式", "净化器晚上声音大怎么办？",
     "按遥控器或 APP 中的「睡眠模式」，风机降至最低转速（噪音<30分贝）并关闭显示灯。也可设置定时，在 22:00-7:00 自动进入睡眠模式。", "产品使用", "净化器,睡眠模式,噪音"),
    ("智能门锁 L2 电池与续航", "门锁用什么电池？能用多久？",
     "使用 8 节 5 号碱性电池（不建议用充电电池，电压不稳），正常使用约 12 个月。电量低于 20% 时门锁语音与 APP 均会提醒，请及时更换。", "产品使用", "门锁,电池"),
    ("产品说明书电子版获取", "说明书丢了去哪里下载？",
     "打开「智家APP」→ 我的 → 帮助中心 → 说明书下载，选择对应产品型号即可查看/下载 PDF 电子说明书。", "产品使用", "说明书"),
    # 故障排查
    ("智能音箱 X1 没有声音", "音箱没声音/声音很小怎么办？",
     "1. 确认音量：说「小智小智，音量调到 50」或旋转顶部音量环；2. 检查是否处于蓝牙模式被静音；3. 重启音箱（拔电 10 秒）；4. 若仍无声，在 APP 中恢复出厂设置后重新配网；仍无效则可能是扬声器故障，请申请保修检测。", "故障排查", "音箱,没声音"),
    ("扫地机器人 S7 不回充", "扫地机扫完不回充电座怎么办？",
     "1. 确认充电座两侧 0.5 米、前方 1.5 米内无障碍物；2. 用干布擦拭充电座极片与机身充电触点；3. 检查充电座指示灯是否常亮（不亮请换插座）；4. 在 APP 重新定位地图后测试「回充」按钮；仍失败建议重置地图或报修。", "故障排查", "扫地机,回充"),
    ("扫地机器人 S7 吸力变小", "扫地机吸力不足怎么办？",
     "多数是耗材堵塞：1. 清空尘盒并水洗滤网（晾干后装回）；2. 清理主刷/边刷缠发；3. 检查吸口是否有异物。滤网建议每 1-2 个月更换。若清理后仍吸力弱，可能是风机故障，建议报修。", "故障排查", "扫地机,吸力"),
    ("空气净化器 A3 有异味", "净化器出风有异味怎么办？",
     "新滤芯前几天有轻微活性炭味属正常。若是酸味/霉味：多为滤芯吸附饱和，请更换滤芯；更换后仍有异味，用干布清洁进出风口与内仓。若为烧焦味请立即断电并联系售后报修。", "故障排查", "净化器,异味"),
    ("智能门锁 L2 指纹识别失灵", "门锁指纹解锁失败/不灵敏怎么办？",
     "1. 用干布擦拭指纹感应区；2. 手指干燥/脱皮会影响识别，可重新录入该手指指纹并多角度按压；3. 电量低于 20% 时识别率下降，请更换电池；4. 若完全无反应，使用应急密码或应急钥匙开门后联系售后。", "故障排查", "门锁,指纹,失灵"),
    ("智能音箱 X1 无法连接WiFi", "音箱连不上网怎么办？",
     "1. 确认路由器为 2.4GHz 频段且密码正确；2. 音箱与路由器距离不超过 8 米；3. 路由器管理页面确认未开启「AP 隔离」；4. 重置音箱网络（长按电源键 10 秒）后重新配网。", "故障排查", "音箱,连不上,WiFi"),
    ("电动牙刷 T5 充不进电", "牙刷放上底座不充电怎么办？",
     "1. 检查底座指示灯是否亮（换插座/换线测试）；2. 擦干牙刷底部与底座水渍；3. 确认牙刷放置到位（磁吸对准）；4. 电池长期亏电需连续充电 2 小时激活。仍无法充电请申请保修。", "故障排查", "牙刷,充电"),
    ("扫地机器人 S7 提示激光头故障", "扫地机报「激光测距异常」怎么办？",
     "1. 检查激光头（顶部凸起）是否被贴纸/胶带遮挡；2. 轻轻转动激光头确认可自由旋转；3. 重启主机。若持续报错为硬件故障，在保修期内可免费维修。", "故障排查", "扫地机,激光"),
    ("APP 无法控制设备", "APP里设备显示离线怎么办？",
     "1. 确认设备通电且家中 WiFi 正常；2. 手机与设备不必同一网络，但设备所连 WiFi 需能上网；3. 路由器重启后设备会自动重连（约 2 分钟）；4. 长时间离线可删除设备重新配网。", "故障排查", "APP,离线"),
    ("智能门锁 L2 门锁没电了", "门锁没电了怎么开门？",
     "门锁底部有 Type-C 应急供电口，用充电宝连接后即可正常输入密码/指纹开门；也可使用随机附赠的应急机械钥匙（钥匙孔在锁体底部盖板内）。开门后请立即更换电池。", "故障排查", "门锁,没电,应急"),
    # 退换货政策
    ("7天无理由退货政策", "退货政策是什么？什么条件能退货？",
     "自签收次日起 7 天内，商品不影响二次销售（外观无损、配件齐全、包装完整）可申请无理由退货。质量问题退货运费由商家承担；无理由退货运费由客户承担。退款在验收通过后 1-3 个工作日原路退回。", "退换货政策", "退货,7天"),
    ("15天换货政策", "换货政策是什么？",
     "自签收次日起 15 天内，商品出现性能故障或质量问题，凭检测结果可申请免费换货（同型号新品）。非质量问题不支持换货。换货物流费用由商家承担。", "退换货政策", "换货,15天"),
    ("退货运费规则", "退货运费谁出？",
     "质量问题退货：商家承担双向运费；7 天无理由退货（非质量问题）：客户承担退回运费，一般 10-20 元。建议使用平台上门取件服务，费用从退款中代扣。", "退换货政策", "退货,运费"),
    ("退款到账时间", "退款多久到账？",
     "商家验收通过后 1-3 个工作日发起退款，原路退回：微信/支付宝实时到账，银行卡 1-5 个工作日。可在订单详情查看退款进度。", "退换货政策", "退款,到账"),
    ("拒收与退回", "快递还没收怎么退？可以拒收吗？",
     "商品未签收时可直接拒收，包裹退回商家后自动全额退款（约 3-7 天）。已下单未发货可联系客服直接取消订单，实时退款。", "退换货政策", "拒收,取消订单"),
    # 保修条款
    ("整机保修期限", "产品保修多久？",
     "智能音箱 X1、空气净化器 A3、电动牙刷 T5 整机保修 12 个月；扫地机器人 S7、智能门锁 L2 整机保修 24 个月。以签收日期起算，保修期内非人为损坏免费维修。", "保修条款", "保修,期限"),
    ("保修范围与免责", "什么情况不在保修范围内？",
     "以下情况不在免费保修范围：人为损坏（进水、摔落、私自拆机）、使用非原装配件导致的故障、超过保修期、无法提供有效购买凭证。耗材（滤芯、滤网、边刷、刷头等）不在整机保修范围内。", "保修条款", "保修,免责"),
    ("过保维修收费标准", "过保了维修怎么收费？",
     "超过保修期的产品支持付费维修：检测费 30 元（维修成交则免收），维修费=配件成本+人工费 50 元起。可先申请维修工单，工程师检测后报价，确认后再维修。", "保修条款", "过保,维修,收费"),
    ("保修凭证", "保修需要什么凭证？发票丢了怎么办？",
     "官方商城订单自动关联电子凭证，无需发票即可保修。第三方渠道购买请提供订单截图或发票照片。无任何凭证时按出厂日期+3 个月估算保修期。", "保修条款", "保修,凭证,发票"),
    ("上门维修服务", "支持上门维修吗？",
     "智能门锁 L2 支持免费上门安装与保修期内上门维修（覆盖全国 300+ 城市）。其他产品为寄修模式：申请维修工单后，顺丰上门取件，修复后寄回，保修期内全程免费。", "保修条款", "上门,维修"),
    # 物流
    ("发货时效", "下单后多久发货？",
     "现货商品 24 小时内发货（大促期间 48 小时）；预售商品按详情页约定时间发货。发货后可在订单详情查看物流单号。", "物流", "发货,时效"),
    ("物流查询", "怎么查物流到哪了？",
     "订单详情页点击「查看物流」可实时跟踪。也可以直接把订单号发给客服查询。默认发顺丰/京东物流，一般 2-4 天送达。", "物流", "物流,查询"),
    ("收货注意事项", "收货时要注意什么？",
     "签收前请检查外包装是否完好，如有明显破损可当场拒收并联系客服补发。大家电类建议当面开箱验货。签收后 48 小时内发现运输损坏，请拍照联系客服处理。", "物流", "收货,验货"),
    ("修改收货地址", "下单后能改地址吗？",
     "未发货前可联系客服修改收货地址；已发货后无法修改，可尝试联系承运快递员协商，或拒收后重新下单。", "物流", "地址,修改"),
    ("发票开具", "怎么开发票？",
     "订单详情页 → 申请开票，支持个人/企业电子普票，开票后发送至预留邮箱。企业专票请联系客服人工处理，需提供开票信息，约 3 个工作日开出。", "物流", "发票"),
]

TREES = [
    dict(product_category="扫地机器人", title="扫地机器人不开机排查",
         symptom_keywords="不开机,开不了机,没反应,不工作,无法启动",
         tree_json={
             "root": "n1",
             "nodes": {
                 "n1": {"ask": "请把扫地机器人放到充电座上，观察充电座指示灯是否亮起？", "options": {"亮": "n2", "不亮": "n3"}},
                 "n2": {"ask": "充电 30 分钟后，长按机身电源键 3 秒，机器有开机提示音或指示灯吗？", "options": {"有": "leaf_ok", "没有": "n4"}},
                 "n3": {"ask": "请更换一个插座并检查电源线接头，充电座指示灯亮了吗？", "options": {"亮了": "n2", "仍不亮": "leaf_dock"}},
                 "n4": {"ask": "请用干布擦拭机身底部充电触点和充电座极片（可能氧化接触不良），再充电 30 分钟后尝试开机，有反应吗？", "options": {"有反应": "leaf_ok", "仍无反应": "leaf_rma"}},
                 "leaf_ok": {"conclusion": "机器已恢复正常，之前应该是电池完全亏电导致，建议避免长时间断电存放。", "action": "resolved"},
                 "leaf_dock": {"conclusion": "初步判断为充电座或电源适配器故障。", "action": "create_rma_repair"},
                 "leaf_rma": {"conclusion": "初步判断为主机电源模块或电池故障。", "action": "create_rma_repair"},
             },
         }),
    dict(product_category="智能音箱", title="智能音箱无法连接WiFi排查",
         symptom_keywords="连不上,无法连接,配网失败,断网,离线",
         tree_json={
             "root": "n1",
             "nodes": {
                 "n1": {"ask": "请确认家里路由器是否有 2.4GHz 频段？（音箱不支持纯 5G WiFi）", "options": {"有/不确定": "n2", "只有5G": "leaf_5g"}},
                 "n2": {"ask": "长按音箱顶部电源键 10 秒重置网络，指示灯变为橙色闪烁了吗？", "options": {"是": "n3", "否": "leaf_rma"}},
                 "n3": {"ask": "用 APP 重新配网，输入 WiFi 密码后是否提示「连接成功」？", "options": {"成功": "leaf_ok", "失败": "n4"}},
                 "n4": {"ask": "请在路由器设置中确认没有开启「AP隔离/访客隔离」，并把音箱移到路由器 3 米内再试，成功了吗？", "options": {"成功": "leaf_ok", "仍失败": "leaf_rma"}},
                 "leaf_ok": {"conclusion": "音箱已成功联网，可以正常使用了。", "action": "resolved"},
                 "leaf_5g": {"conclusion": "请在路由器管理页开启 2.4GHz 频段（或联系宽带师傅协助），再进行配网即可。", "action": "resolved"},
                 "leaf_rma": {"conclusion": "排查后仍无法配网，疑似 WiFi 模块故障。", "action": "create_rma_repair"},
             },
         }),
    dict(product_category="空气净化器", title="空气净化器异味排查",
         symptom_keywords="异味,怪味,臭味,酸味,霉味",
         tree_json={
             "root": "n1",
             "nodes": {
                 "n1": {"ask": "请问异味是哪种类型？", "options": {"烧焦味": "leaf_burn", "酸味/霉味": "n2", "轻微炭味": "leaf_carbon"}},
                 "n2": {"ask": "滤芯使用超过 6 个月了吗？（APP 可查看滤芯寿命）", "options": {"超过": "leaf_filter", "没超过": "n3"}},
                 "n3": {"ask": "取出滤芯，闻一下异味来自滤芯还是机身内仓？", "options": {"滤芯": "leaf_filter", "机身": "leaf_clean"}},
                 "leaf_burn": {"conclusion": "烧焦味有安全风险，请立即断电停用！需要尽快安排检修。", "action": "create_rma_repair"},
                 "leaf_carbon": {"conclusion": "新滤芯前 1-2 周有轻微活性炭味属于正常现象，通风使用几天即可消散。", "action": "resolved"},
                 "leaf_filter": {"conclusion": "滤芯吸附饱和产生异味，更换新滤芯即可解决。您可以在商城搜索「A3滤芯」购买。", "action": "resolved"},
                 "leaf_clean": {"conclusion": "机身内仓有污染，请断电后用干布清洁内仓与出风口；清洁后若仍有异味建议报修检测。", "action": "resolved"},
             },
         }),
    dict(product_category="智能门锁", title="智能门锁指纹失灵排查",
         symptom_keywords="指纹失灵,指纹识别,解锁失败,指纹没反应",
         tree_json={
             "root": "n1",
             "nodes": {
                 "n1": {"ask": "按压指纹区时，门锁有语音或灯光反馈吗？", "options": {"有反馈但识别失败": "n2", "完全没反应": "n3"}},
                 "n2": {"ask": "请用干布擦拭指纹感应区，并擦干手指再试，能识别了吗？", "options": {"可以了": "leaf_ok", "还是不行": "n4"}},
                 "n3": {"ask": "门锁电量是否充足？（低电量时会先播报提醒）", "options": {"电量充足": "leaf_rma", "电量低/不确定": "leaf_battery"}},
                 "n4": {"ask": "请重新录入这枚指纹（多角度按压6次）后再试，识别正常了吗？", "options": {"正常了": "leaf_ok", "仍失败": "leaf_rma"}},
                 "leaf_ok": {"conclusion": "指纹识别已恢复正常。日常注意保持感应区清洁、手指干燥。", "action": "resolved"},
                 "leaf_battery": {"conclusion": "请更换 8 节全新 5 号碱性电池后再试（没电时可用底部 Type-C 口接充电宝应急供电）。", "action": "resolved"},
                 "leaf_rma": {"conclusion": "疑似指纹模块硬件故障。", "action": "create_rma_repair"},
             },
         }),
]

# 工单：(customer_idx, title, category, priority, status, days_ago, 流水备注链)
TICKETS = [
    (1, "音箱屏幕闪烁需检测", "故障报修", "中", "待处理", 1, []),
    (3, "净化器滤芯购买咨询", "其他", "低", "待处理", 2, []),
    (6, "包裹显示签收但未收到", "物流咨询", "高", "待处理", 0, []),
    (0, "扫地机器人边刷异响", "故障报修", "中", "处理中", 3, ["已联系客户确认故障现象"]),
    (2, "门锁安装师傅预约", "其他", "中", "处理中", 4, ["已分配安装师傅，待预约时间"]),
    (4, "退货运费争议", "投诉建议", "高", "处理中", 2, ["已核实订单，与客户协商中"]),
    (5, "音箱固件升级失败", "故障报修", "中", "处理中", 5, ["技术组远程排查中"]),
    (1, "换货物流单号查询", "退换货", "低", "待客户确认", 6, ["已发出换货商品", "待客户确认收货"]),
    (7, "牙刷刷头卡扣松动", "故障报修", "低", "待客户确认", 7, ["已寄出新刷头配件", "请客户确认是否解决"]),
    (0, "净化器噪音检测", "故障报修", "中", "已解决", 10, ["寄修检测完成，更换风机", "客户确认问题解决"]),
    (2, "发票抬头修改", "其他", "低", "已解决", 12, ["已重新开具发票发送邮箱", "客户确认收到"]),
    (5, "APP无法登录", "故障报修", "高", "已解决", 15, ["重置账号后恢复正常", "客户确认可以登录"]),
    (3, "物流破损理赔", "物流咨询", "高", "已关闭", 20, ["已完成理赔补发", "客户确认收货", "工单归档"]),
    (6, "投诉客服响应慢", "投诉建议", "紧急", "已关闭", 25, ["主管回访致歉", "客户接受处理结果", "工单归档"]),
    (4, "门锁电池更换教学", "其他", "低", "已关闭", 28, ["电话指导完成", "客户确认解决", "工单归档"]),
]

# 历史会话（学习分析素材）：(customer_idx, days_ago, resolved预期, [(role, text), ...])
HISTORY_CONVERSATIONS = [
    (1, 9, True, [
        ("user", "智能音箱X1可以同时连接两台手机的蓝牙吗？"),
        ("assistant", "您好！智能音箱 X1 支持记忆 8 台配对设备，但同一时间只能连接 1 台手机播放。切换设备时，在新手机的蓝牙列表点击「智能音箱X1」即可自动断开旧连接并切换，无需重新配对。"),
        ("user", "那有没有办法快速切换？"),
        ("assistant", "有的，您可以对音箱说「小智小智，连接我的手机」，音箱会自动连接最近使用的设备；或在智家APP的设备页点击「蓝牙管理」手动选择要连接的手机，比在手机蓝牙设置里操作更快捷。"),
        ("user", "明白了，谢谢"),
        ("assistant", "不客气！还有其他问题随时找我，祝您使用愉快 😊"),
    ]),
    (4, 8, True, [
        ("user", "扫地机器人S7怎么设置每天定时清扫？"),
        ("assistant", "您好！设置定时清扫步骤：打开智家APP → 进入扫地机器人 S7 设备页 → 点击「定时清扫」→ 新建定时任务，选择每天的清扫时间（如上午10:00）和清扫模式，保存后机器人每天会自动开始清扫。您还可以为工作日和周末分别设置不同时间。"),
        ("user", "可以设置只扫客厅吗"),
        ("assistant", "可以的！在定时任务设置中选择「指定区域」，然后在地图上勾选客厅区域即可。前提是已完成首次建图并在地图编辑中划分好了房间。"),
        ("user", "设置好了，谢谢"),
        ("assistant", "太好了！还有其他需要帮助的吗？"),
    ]),
    (5, 8, True, [
        ("user", "电动牙刷T5第一次用需要充满电吗？"),
        ("assistant", "您好！T5 出厂自带约 50% 电量，可以直接使用。不过建议首次使用前充满电（约 4 小时，指示灯常亮即充满），有助于电池校准，之后正常充电即可。"),
        ("user", "好的"),
        ("assistant", "不客气，祝您使用愉快！"),
    ]),
    (2, 7, True, [
        ("user", "智能门锁突然没电了人在门外怎么办？"),
        ("assistant", "您好，别着急！两种应急方案：① 门锁底部有 Type-C 应急供电口，用充电宝+数据线连接后，门锁即可临时通电，正常输入密码或指纹开门；② 使用随机附赠的应急机械钥匙（钥匙孔在锁体底部盖板内侧）。开门后请尽快更换 8 节 5 号碱性电池。"),
        ("user", "充电宝真的可以，开了，太感谢了"),
        ("assistant", "太好了！记得及时换电池哦，门锁电量低于 20% 时 APP 和门锁都会提前提醒，留意提醒可以避免这种情况。还有什么可以帮您？"),
        ("user", "没有了，服务很好，5分"),
        ("assistant", "感谢您的认可！祝您生活愉快 😊"),
    ]),
    (6, 6, True, [
        ("user", "你们的智能音箱有儿童模式吗？想给孩子买一个"),
        ("assistant", "您好！智能音箱 X1 有「儿童模式」：开启后会过滤不适宜内容、限制使用时长（可设置每日上限）、并切换为儿童音色和儿童内容库（儿歌、故事、百科问答）。在智家APP → 设备设置 → 儿童模式中开启，还支持设置免打扰时段保护孩子睡眠。"),
        ("user", "内容需要额外付费吗？"),
        ("assistant", "基础儿童内容库（3万+儿歌故事）是免费的；部分名家有声书和课程内容需要开通会员（首月免费体验）。免费内容对日常使用已经很充足了。"),
        ("user", "好的了解了"),
        ("assistant", "不客气！如果决定购买，新用户下单还有优惠活动，可以留意商城首页。还有其他问题吗？"),
    ]),
    (3, 5, False, [
        ("user", "音箱蓝牙连上了但老是自动断开，几分钟就断一次"),
        ("assistant", "您好，我先帮您排查：请确认手机与音箱距离在 8 米内且中间无金属遮挡，并尝试删除配对记录后重新配对。"),
        ("user", "都试过了，还是断，手机就放在音箱旁边"),
        ("assistant", "很抱歉，我在知识库中没有找到这个问题的进一步解决方案。这种持续性断连可能与固件版本或硬件有关，我为您转接人工客服深入处理。"),
        ("user", "行吧"),
        ("assistant", "已为您转接人工客服并创建工单，技术专员会在今天内联系您，抱歉给您带来不便。"),
    ]),
    (7, 5, False, [
        ("user", "扫地机器人的拖布支架怎么拆下来清洗？卡得很紧"),
        ("assistant", "您好，我帮您查询一下拖布支架的拆卸方法。"),
        ("assistant", "抱歉，知识库中未找到 S7 拖布支架拆卸的详细图文说明。一般是按住支架两侧卡扣向外平拉即可取下，请不要垂直用力以免损坏卡扣。如果仍然拆不下来，我帮您转接人工客服获取视频指导？"),
        ("user", "嗯需要视频"),
        ("assistant", "好的，已为您转接人工客服，稍后会有专员发送拆卸教学视频给您。"),
    ]),
    (0, 4, False, [
        ("user", "我要投诉！上周买的净化器到现在物流一点动静都没有"),
        ("assistant", "非常抱歉给您带来不好的体验！我立即为您查询订单物流状态。"),
        ("assistant", "查询到您的订单物流信息已 5 天未更新，确实异常。我已为您创建高优先级工单并转接人工客服，会催促物流核查包裹去向，最迟明天给您答复；若包裹丢失将优先为您补发。"),
        ("user", "尽快，等着用"),
        ("assistant", "理解您的心情，已标记加急处理。给您带来不便再次致歉。"),
    ]),
    (5, 3, False, [
        ("user", "空气净化器开到3档以上就有嗡嗡的共振声，1、2档没有"),
        ("assistant", "您好，请先检查：① 机器是否放置在平整硬质地面（地毯会引起共振）；② 背部滤芯仓盖是否完全扣紧；③ 滤芯是否卡到位。"),
        ("user", "都检查了，地面平的，盖子也紧，还是响"),
        ("assistant", "感谢您的配合排查。高档位共振声可能与风机动平衡有关，属于需要检测的硬件问题。很抱歉暂时无法远程解决，我为您转接人工客服安排检测，保修期内检测与维修均免费。"),
        ("user", "那安排吧"),
        ("assistant", "已为您创建检测工单并转接人工，顺丰会上门取件，检测结果出来会第一时间通知您。"),
    ]),
    (2, 2, True, [
        ("user", "净化器的滤芯多久换一次？APP显示寿命还剩30%"),
        ("assistant", "您好！A3 滤芯建议每 6-12 个月更换一次，具体看使用环境。APP 显示剩余 30% 说明还可以继续使用约 1-2 个月，寿命归零前 APP 会推送更换提醒。您可以提前在商城搜索「A3滤芯」备货，会员购买滤芯享 9 折。"),
        ("user", "换滤芯麻烦吗？"),
        ("assistant", "很简单，3 分钟搞定：断电 → 打开背部滤芯仓盖 → 逆时针旋出旧滤芯 → 新滤芯撕掉塑封装入 → 长按机身「滤芯重置」键 5 秒即可。新滤芯包装里也有图文说明。"),
        ("user", "好的谢谢"),
        ("assistant", "不客气！还有其他问题随时找我 😊"),
    ]),
]

# 满意度：(history_conv_index, score, comment, days_ago)
RATINGS = [
    (0, 5, "回答很清楚", 9),
    (1, 5, "定时设置成功了", 8),
    (2, 4, "", 8),
    (3, 5, "应急方法太实用了", 7),
    (4, 5, "介绍很详细", 6),
    (5, 2, "问题没解决还要等人工", 5),
    (7, 1, "物流太慢了", 4),
    (8, 3, "还要寄修，麻烦", 3),
]

PRESET_CANDIDATES = [
    dict(type="faq", question="扫地机器人集尘袋多久更换一次？",
         suggested_answer="自动集尘座的集尘袋建议每 1-2 个月更换一次（视使用频率与家中灰尘量），APP 会在集尘袋将满时推送提醒。更换时按住集尘仓盖开关取出旧袋，新袋插入到位即可，全程不沾灰。",
         category="产品使用", confidence=0.72, frequency=2),
    dict(type="kb_gap", question="智家APP 如何接收设备离线通知？",
         suggested_answer=None, category="产品使用", confidence=0.5, frequency=1,
         review_note="多位客户询问设备离线是否能推送提醒，现有知识库未覆盖"),
]


def seed_if_empty():
    init_db()
    db = SessionLocal()
    try:
        if db.query(Customer).count() > 0:
            return
        print("  首次运行：正在写入演示数据…")

        products = [Product(**p) for p in PRODUCTS]
        db.add_all(products)
        customers = [Customer(**c) for c in CUSTOMERS]
        db.add_all(customers)
        db.flush()

        # 订单
        for i, (ci, pi, ddays, status) in enumerate(ORDERS, start=1):
            delivered = _days_ago(ddays) if ddays is not None else None
            purchased = (delivered - timedelta(days=3)) if delivered else _days_ago(2)
            db.add(Order(
                order_no=f"SO{purchased.strftime('%Y%m%d')}-{i:04d}",
                customer_id=customers[ci].id, product_id=products[pi].id,
                quantity=1, amount=products[pi].price, status=status,
                purchased_at=purchased, delivered_at=delivered))

        # 知识库
        for title, question, answer, category, tags in KB_ENTRIES:
            entry_type = "troubleshooting" if category == "故障排查" else \
                         "policy" if category in ("退换货政策", "保修条款") else "faq"
            e = KbEntry(title=title, question=question, answer=answer,
                        category=category, tags=tags, entry_type=entry_type,
                        source="seed", status="published",
                        hit_count=(hash(title) % 20))
            db.add(e)
            db.flush()
            kb_search.upsert_index(db, e)

        # 排查树
        for t in TREES:
            db.add(TroubleshootingTree(
                product_category=t["product_category"], title=t["title"],
                symptom_keywords=t["symptom_keywords"],
                tree_json=json.dumps(t["tree_json"], ensure_ascii=False)))

        # 工单
        status_chain = {"待处理": ["待处理"],
                        "处理中": ["待处理", "处理中"],
                        "待客户确认": ["待处理", "处理中", "待客户确认"],
                        "已解决": ["待处理", "处理中", "待客户确认", "已解决"],
                        "已关闭": ["待处理", "处理中", "待客户确认", "已解决", "已关闭"]}
        for i, (ci, title, category, priority, status, days, notes) in enumerate(TICKETS, start=1):
            created = _days_ago(days, hour=9)
            t = Ticket(ticket_no=f"TK{created.strftime('%Y%m%d')}-{i:04d}",
                       customer_id=customers[ci].id, title=title, description=title,
                       category=category, priority=priority, status=status,
                       created_at=created, updated_at=created,
                       resolved_at=created if status in ("已解决", "已关闭") else None)
            db.add(t)
            db.flush()
            chain = status_chain[status]
            prev = None
            for j, st in enumerate(chain):
                note = "工单创建" if j == 0 else (notes[j - 1] if j - 1 < len(notes) else "")
                db.add(TicketEvent(ticket_id=t.id, from_status=prev, to_status=st,
                                   note=note, operator="AI助手" if j == 0 else "客服",
                                   created_at=created + timedelta(hours=j * 5)))
                prev = st

        # 演示 RMA 两条（管理端退换货页开箱不空）
        orders = db.query(Order).all()
        o1 = next(o for o in orders if o.customer_id == customers[1].id and o.delivered_at)
        r1 = RmaRequest(rma_no=f"RMA{_days_ago(2).strftime('%Y%m%d')}-0001",
                        order_id=o1.id, customer_id=o1.customer_id, type="退货",
                        reason="不喜欢音质，无理由退货", status="已提交",
                        refund_amount=o1.amount, created_at=_days_ago(2), updated_at=_days_ago(2))
        db.add(r1)
        db.flush()
        db.add(RmaEvent(rma_id=r1.id, from_status=None, to_status="已提交",
                        note="退货申请提交", operator="AI助手", created_at=_days_ago(2)))
        o2 = next(o for o in orders if o.customer_id == customers[3].id and o.delivered_at
                  and o.id != o1.id)
        r2 = RmaRequest(rma_no=f"RMA{_days_ago(6).strftime('%Y%m%d')}-0001",
                        order_id=o2.id, customer_id=o2.customer_id, type="维修",
                        reason="高档位共振异响", status="处理中",
                        created_at=_days_ago(6), updated_at=_days_ago(1))
        db.add(r2)
        db.flush()
        prev = None
        for j, st in enumerate(["已提交", "已批准", "待寄回", "已收货", "处理中"]):
            db.add(RmaEvent(rma_id=r2.id, from_status=prev, to_status=st,
                            note=["维修申请提交", "审核通过", "请寄回商品", "已收到寄回商品", "工程师检测维修中"][j],
                            operator="AI助手" if j == 0 else "客服",
                            created_at=_days_ago(6) + timedelta(days=j)))
            prev = st

        # 历史会话（学习素材）
        conv_objs = []
        for ci, days, _resolved, msgs in HISTORY_CONVERSATIONS:
            created = _days_ago(days, hour=14)
            conv = Conversation(customer_id=customers[ci].id, status="closed",
                                title=msgs[0][1][:40], analyzed=False,
                                handed_off=any("转接人工" in t for r, t in msgs if r == "assistant"),
                                created_at=created, closed_at=created + timedelta(minutes=15))
            db.add(conv)
            db.flush()
            for k, (role, text) in enumerate(msgs):
                db.add(Message(conversation_id=conv.id, role=role, display_text=text,
                               created_at=created + timedelta(minutes=k)))
            conv_objs.append(conv)

        # 满意度
        for conv_idx, score, comment, days in RATINGS:
            conv = conv_objs[conv_idx]
            db.add(SatisfactionRating(conversation_id=conv.id,
                                      customer_id=conv.customer_id,
                                      score=score, comment=comment,
                                      created_at=_days_ago(days, hour=15)))

        # 预置学习候选
        for c in PRESET_CANDIDATES:
            db.add(LearningCandidate(**c))

        db.commit()
        print(f"  演示数据就绪：{len(CUSTOMERS)} 位客户 / {len(ORDERS)} 笔订单 / "
              f"{len(KB_ENTRIES)} 条知识 / {len(TICKETS)} 个工单 / "
              f"{len(HISTORY_CONVERSATIONS)} 条历史会话")
    finally:
        db.close()


if __name__ == "__main__":
    seed_if_empty()
