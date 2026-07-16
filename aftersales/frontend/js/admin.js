/* 管理控制台（员工登录 + 角色化导航 + 人工工作台 + 主动提醒） */
const { createApp } = Vue;

createApp({
  data() {
    return {
      mode: { mock: true, model: "" },
      me: null,             // 登录员工 {name, role, role_name}
      loginUser: "",
      loginPass: "",
      loginError: "",
      demoStaff: [],
      tab: "dashboard",
      tabs: [
        { key: "dashboard", name: "数据分析", icon: "📊", roles: ["admin", "agent", "ops"] },
        { key: "workbench", name: "人工工作台", icon: "🎧", roles: ["admin", "agent"] },
        { key: "tickets", name: "工单看板", icon: "🎫", roles: ["admin", "agent"] },
        { key: "rma", name: "退换货管理", icon: "📦", roles: ["admin", "agent"] },
        { key: "kb", name: "知识库", icon: "📚", roles: ["admin", "ops"] },
        { key: "learning", name: "学习审核", icon: "🎓", roles: ["admin", "ops"] },
        { key: "reminders", name: "主动提醒", icon: "📣", roles: ["admin", "agent", "ops"] },
        { key: "conversations", name: "会话记录", icon: "💬", roles: ["admin", "agent", "ops"] },
      ],
      toast: "",
      customers: [],
      // dashboard
      ov: {},
      charts: {},
      // workbench
      wbQueue: { waiting: [], serving: [] },
      wbConv: null,
      wbMessages: [],
      wbDraft: "",
      wbSuggesting: false,
      _wbTimer: null,
      _wbLastMsgId: 0,
      // tickets
      tickets: [],
      ticketStatuses: ["待处理", "处理中", "待客户确认", "已解决", "已关闭"],
      ticketDetail: null,
      ticketModal: { show: false },
      // rma
      rmas: [],
      rmaFilter: "",
      rmaStatuses: ["已提交", "已批准", "待寄回", "已收货", "处理中", "已完成", "已驳回", "已取消"],
      rmaDetail: null,
      // kb
      kbItems: [],
      kbTotal: 0,
      kbQuery: "",
      kbCategory: "",
      kbSource: "",
      kbSearchMode: false,
      kbManualHits: [],
      manuals: [],
      manualUploading: false,
      manualPreview: null,
      kbCategories: ["产品使用", "故障排查", "退换货政策", "保修条款", "物流", "其他"],
      kbModal: { show: false },
      // learning
      candidates: [],
      candStatus: "pending",
      lastRun: null,
      analyzing: false,
      approveModal: { show: false },
      _runTimer: null,
      // reminders
      reminders: [],
      reminderFilter: "",
      // conversations
      convs: [],
      convReplay: null,
      qaRunning: null,
    };
  },
  computed: {
    visibleTabs() {
      if (!this.me) return [];
      return this.tabs.filter(t => t.roles.includes(this.me.role));
    },
  },
  async mounted() {
    api.onUnauthorized = () => this.forceLogin();
    this.mode = await api.get("/api/meta/mode");
    try {
      const demo = await api.get("/api/auth/demo-accounts");
      this.demoStaff = demo.staff || [];
    } catch (e) { /* ignore */ }
    const saved = localStorage.getItem("staff_token");
    const info = localStorage.getItem("staff_info");
    if (saved && info) {
      api.token = saved;
      this.me = JSON.parse(info);
      await this.afterLogin();
    }
    this._wbTimer = setInterval(() => this.wbPoll(), 2500);
  },
  methods: {
    renderText,
    showToast(msg) {
      this.toast = msg;
      setTimeout(() => (this.toast = ""), 2600);
    },
    forceLogin() {
      api.token = null;
      this.me = null;
      localStorage.removeItem("staff_token");
      localStorage.removeItem("staff_info");
    },
    async login() {
      this.loginError = "";
      try {
        const res = await api.post("/api/auth/staff/login",
          { username: this.loginUser, password: this.loginPass });
        api.token = res.token;
        this.me = res.staff;
        localStorage.setItem("staff_token", res.token);
        localStorage.setItem("staff_info", JSON.stringify(res.staff));
        await this.afterLogin();
      } catch (e) {
        this.loginError = e.message;
      }
    },
    async logout() {
      try { await api.post("/api/auth/logout"); } catch (e) { /* ignore */ }
      this.forceLogin();
    },
    async afterLogin() {
      if (!this.visibleTabs.find(t => t.key === this.tab)) {
        this.tab = this.visibleTabs[0] ? this.visibleTabs[0].key : "dashboard";
      }
      try {
        const res = await api.get("/api/meta/customers");
        this.customers = res.items;
      } catch (e) { /* ops 无此权限时忽略 */ }
      await this.switchTab(this.tab);
    },
    async switchTab(key) {
      this.tab = key;
      if (key === "dashboard") await this.loadDashboard();
      if (key === "workbench") await this.loadWbQueue();
      if (key === "tickets") await this.loadTickets();
      if (key === "rma") await this.loadRma();
      if (key === "kb") await this.loadKb();
      if (key === "learning") { await this.loadCandidates(); await this.loadRuns(); }
      if (key === "reminders") await this.loadReminders();
      if (key === "conversations") await this.loadConvs();
    },

    /* ---------- 仪表盘 ---------- */
    async loadDashboard() {
      const [ov, trends, hot, dist, sat] = await Promise.all([
        api.get("/api/analytics/overview"),
        api.get("/api/analytics/trends?days=30"),
        api.get("/api/analytics/hot-issues?days=30"),
        api.get("/api/analytics/distribution"),
        api.get("/api/satisfaction/stats"),
      ]);
      this.ov = ov;
      this.$nextTick(() => this.renderCharts(trends, hot, dist, sat));
    },
    chart(id) {
      const el = document.getElementById(id);
      if (!el) return null;
      if (!this.charts[id]) this.charts[id] = echarts.init(el);
      return this.charts[id];
    },
    renderCharts(trends, hot, dist, sat) {
      const c1 = this.chart("chart-trend");
      c1 && c1.setOption({
        tooltip: { trigger: "axis" },
        legend: { data: ["会话", "工单"], top: 0 },
        grid: { left: 40, right: 20, top: 34, bottom: 28 },
        xAxis: { type: "category", data: trends.labels },
        yAxis: { type: "value", minInterval: 1 },
        series: [
          { name: "会话", type: "line", smooth: true, data: trends.conversations,
            areaStyle: { opacity: .12 }, itemStyle: { color: "#2563eb" } },
          { name: "工单", type: "line", smooth: true, data: trends.tickets,
            itemStyle: { color: "#ea580c" } },
        ],
      });
      const items = (hot.items || []).slice().reverse();
      const c2 = this.chart("chart-hot");
      c2 && c2.setOption({
        tooltip: {},
        grid: { left: 130, right: 30, top: 10, bottom: 28 },
        xAxis: { type: "value", minInterval: 1 },
        yAxis: { type: "category", data: items.map(i => i.tag) },
        series: [{ type: "bar", data: items.map(i => i.count), barWidth: 14,
                   itemStyle: { color: "#f59e0b", borderRadius: 4 },
                   label: { show: true, position: "right" } }],
      });
      const cat = dist.ticket_category || {};
      const c3 = this.chart("chart-cat");
      c3 && c3.setOption({
        tooltip: { trigger: "item" },
        legend: { bottom: 0 },
        series: [{ type: "pie", radius: ["38%", "62%"],
                   data: Object.entries(cat).map(([name, value]) => ({ name, value })),
                   label: { formatter: "{b}: {c}" } }],
      });
      const c4 = this.chart("chart-sat");
      c4 && c4.setOption({
        series: [{
          type: "gauge", min: 1, max: 5, splitNumber: 4,
          axisLine: { lineStyle: { width: 14, color: [[.4, "#fca5a5"], [.7, "#fcd34d"], [1, "#86efac"]] } },
          pointer: { width: 5 },
          detail: { formatter: "{value} 分", fontSize: 22, offsetCenter: [0, "62%"] },
          data: [{ value: sat.avg || 0, name: `共 ${sat.count} 条评价` }],
          title: { offsetCenter: [0, "88%"], fontSize: 12 },
        }],
      });
    },

    /* ---------- 人工工作台 ---------- */
    async loadWbQueue() {
      if (!this.me || !["admin", "agent"].includes(this.me.role)) return;
      try {
        this.wbQueue = await api.get("/api/workbench/queue");
      } catch (e) { /* ignore */ }
    },
    async wbOpen(c) {
      const res = await api.get(`/api/conversations/${c.id}/messages`);
      this.wbConv = res.conversation;
      this.wbMessages = res.messages;
      this._wbLastMsgId = res.messages.length ? res.messages[res.messages.length - 1].id : 0;
      this.wbScroll();
    },
    wbScroll() {
      this.$nextTick(() => {
        const el = this.$refs.wbMsgList;
        if (el) el.scrollTop = el.scrollHeight;
      });
    },
    async wbPoll() {
      if (!this.me || this.tab !== "workbench") return;
      await this.loadWbQueue();
      if (!this.wbConv) return;
      try {
        const res = await api.get(`/api/conversations/${this.wbConv.id}/messages`);
        const last = res.messages.length ? res.messages[res.messages.length - 1].id : 0;
        if (last > this._wbLastMsgId ||
            res.conversation.mode !== this.wbConv.mode ||
            res.conversation.status !== this.wbConv.status) {
          this.wbConv = res.conversation;
          this.wbMessages = res.messages;
          this._wbLastMsgId = last;
          this.wbScroll();
        }
      } catch (e) { /* ignore */ }
    },
    async wbTakeover() {
      try {
        await api.post(`/api/workbench/conversations/${this.wbConv.id}/takeover`);
        this.showToast("已接管会话");
        await this.wbOpen(this.wbConv);
        await this.loadWbQueue();
      } catch (e) { this.showToast(e.message); }
    },
    async wbRelease() {
      try {
        await api.post(`/api/workbench/conversations/${this.wbConv.id}/release`);
        this.showToast("已交还 AI 助手");
        await this.wbOpen(this.wbConv);
        await this.loadWbQueue();
      } catch (e) { this.showToast(e.message); }
    },
    async wbFinish() {
      if (!confirm("确定结束该会话？")) return;
      try {
        await api.post(`/api/workbench/conversations/${this.wbConv.id}/finish`);
        this.showToast("会话已结束");
        this.wbConv = null;
        this.wbMessages = [];
        await this.loadWbQueue();
      } catch (e) { this.showToast(e.message); }
    },
    async wbReply() {
      const text = this.wbDraft.trim();
      if (!text || !this.wbConv) return;
      this.wbDraft = "";
      try {
        await api.post(`/api/workbench/conversations/${this.wbConv.id}/reply`, { text });
        await this.wbOpen(this.wbConv);
      } catch (e) { this.showToast(e.message); }
    },
    async wbSuggest() {
      this.wbSuggesting = true;
      try {
        const res = await api.post(`/api/workbench/conversations/${this.wbConv.id}/suggest`);
        this.wbDraft = res.suggestion;
        this.showToast("已生成推荐话术，可编辑后发送");
      } catch (e) {
        this.showToast(e.message);
      } finally {
        this.wbSuggesting = false;
      }
    },

    /* ---------- 工单 ---------- */
    async loadTickets() {
      const res = await api.get("/api/tickets");
      this.tickets = res.items;
    },
    ticketsByStatus(st) {
      return this.tickets.filter(t => t.status === st);
    },
    async moveTicket(t, ns) {
      try {
        await api.patch(`/api/tickets/${t.ticket_no}`, { status: ns });
        this.showToast(`工单 ${t.ticket_no} → ${ns}`);
        await this.loadTickets();
      } catch (e) { this.showToast(e.message); }
    },
    async openTicket(t) {
      this.ticketDetail = await api.get(`/api/tickets/${t.ticket_no}`);
    },
    async moveTicketDetail(ns) {
      try {
        await api.patch(`/api/tickets/${this.ticketDetail.ticket_no}`, { status: ns });
        this.ticketDetail = await api.get(`/api/tickets/${this.ticketDetail.ticket_no}`);
        await this.loadTickets();
      } catch (e) { this.showToast(e.message); }
    },
    async createTicket() {
      try {
        if (!this.ticketModal.title) return this.showToast("请填写标题");
        await api.post("/api/tickets", this.ticketModal);
        this.ticketModal.show = false;
        this.showToast("工单已创建");
        await this.loadTickets();
      } catch (e) { this.showToast(e.message); }
    },

    /* ---------- RMA ---------- */
    async loadRma() {
      const res = await api.get("/api/rma" + (this.rmaFilter ? `?status=${encodeURIComponent(this.rmaFilter)}` : ""));
      this.rmas = res.items;
    },
    async moveRma(r, ns) {
      try {
        await api.patch(`/api/rma/${r.rma_no}`, { status: ns, note: `管理端操作：${ns}` });
        this.showToast(`${r.rma_no} → ${ns}`);
        await this.loadRma();
      } catch (e) { this.showToast(e.message); }
    },
    async openRma(r) {
      this.rmaDetail = await api.get(`/api/rma/${r.rma_no}`);
    },
    async moveRmaDetail(ns) {
      try {
        await api.patch(`/api/rma/${this.rmaDetail.rma_no}`, { status: ns, note: `管理端操作：${ns}` });
        this.rmaDetail = await api.get(`/api/rma/${this.rmaDetail.rma_no}`);
        await this.loadRma();
      } catch (e) { this.showToast(e.message); }
    },

    /* ---------- 知识库 ---------- */
    async loadKb() {
      const params = new URLSearchParams();
      const q = this.kbQuery.trim();
      if (q) params.set("q", q);
      if (this.kbCategory) params.set("category", this.kbCategory);
      if (this.kbSource) params.set("source", this.kbSource);
      const res = await api.get("/api/kb?" + params.toString());
      this.kbItems = res.items;
      this.kbTotal = res.total;
      this.kbSearchMode = res.search;
      this.kbManualHits = [];
      if (q) {
        const mh = await api.get("/api/manuals/search?q=" + encodeURIComponent(q));
        this.kbManualHits = mh.items;
      }
      await this.loadManuals();
    },
    async loadManuals() {
      const res = await api.get("/api/manuals");
      this.manuals = res.items;
    },
    async uploadManual(ev) {
      const file = ev.target.files[0];
      ev.target.value = "";
      if (!file) return;
      this.manualUploading = true;
      try {
        const fd = new FormData();
        fd.append("file", file);
        const doc = await api.upload("/api/manuals", fd);
        this.showToast(`✅ 《${doc.title}》已解析为 ${doc.chunk_count} 个知识块，AI 即刻可用`);
        await this.loadManuals();
      } catch (e) {
        this.showToast(e.message);
      } finally {
        this.manualUploading = false;
      }
    },
    async previewManual(m) {
      this.manualPreview = await api.get(`/api/manuals/${m.id}/chunks`);
    },
    async deleteManual(m) {
      if (!confirm(`确定删除手册《${m.title}》？相关知识块将一并移除。`)) return;
      await api.del(`/api/manuals/${m.id}`);
      this.showToast("已删除");
      await this.loadManuals();
    },
    async digestManual(m) {
      try {
        const res = await api.post(`/api/manuals/${m.id}/digest`);
        this.showToast(res.message);
      } catch (e) { this.showToast(e.message); }
    },
    editKb(e) {
      this.kbModal = e
        ? { show: true, id: e.id, title: e.title, question: e.question, answer: e.answer,
            category: e.category, tags: e.tags || "", status: e.status || "published", entry_type: e.entry_type || "faq" }
        : { show: true, id: null, title: "", question: "", answer: "",
            category: "产品使用", tags: "", status: "published", entry_type: "faq" };
    },
    async saveKb() {
      const m = this.kbModal;
      if (!m.title || !m.answer) return this.showToast("标题与答案必填");
      const payload = { title: m.title, question: m.question, answer: m.answer,
                        category: m.category, tags: m.tags, status: m.status, entry_type: m.entry_type };
      try {
        if (m.id) await api.put(`/api/kb/${m.id}`, payload);
        else await api.post("/api/kb", payload);
        this.kbModal.show = false;
        this.showToast("已保存");
        await this.loadKb();
      } catch (e) { this.showToast(e.message); }
    },
    async deleteKb(e) {
      if (!confirm(`确定删除「${e.title}」？`)) return;
      await api.del(`/api/kb/${e.id}`);
      this.showToast("已删除");
      await this.loadKb();
    },
    async reindexKb() {
      const res = await api.post("/api/kb/reindex");
      this.showToast(`索引已重建（知识 ${res.indexed} 条，手册补向量 ${res.manual_chunks_embedded} 块）`);
    },

    /* ---------- 学习审核 ---------- */
    async loadCandidates() {
      const res = await api.get(`/api/learning/candidates?status=${this.candStatus}`);
      this.candidates = res.items;
    },
    async loadRuns() {
      const res = await api.get("/api/learning/runs");
      this.lastRun = res.items[0] || null;
      this.analyzing = this.lastRun && this.lastRun.status === "running";
      if (this.analyzing && !this._runTimer) {
        this._runTimer = setInterval(async () => {
          await this.loadRuns();
          if (!this.analyzing) {
            clearInterval(this._runTimer);
            this._runTimer = null;
            await this.loadCandidates();
            this.showToast("分析完成");
          }
        }, 1500);
      }
    },
    async startAnalysis() {
      try {
        await api.post("/api/learning/analyze");
        this.analyzing = true;
        this.showToast("分析任务已启动");
        await this.loadRuns();
      } catch (e) { this.showToast(e.message); }
    },
    openApprove(c) {
      this.approveModal = { show: true, id: c.id, question: c.question,
                            answer: c.suggested_answer || "", category: c.category };
    },
    async submitApprove() {
      const m = this.approveModal;
      if (!m.answer.trim()) return this.showToast("答案不能为空");
      try {
        await api.post(`/api/learning/candidates/${m.id}/approve`,
          { question: m.question, answer: m.answer, category: m.category });
        this.approveModal.show = false;
        this.showToast("✅ 已入库知识库，AI 下次回答即可使用");
        await this.loadCandidates();
      } catch (e) { this.showToast(e.message); }
    },
    async rejectCandidate(c) {
      const note = prompt("驳回原因（选填）：") || "";
      try {
        await api.post(`/api/learning/candidates/${c.id}/reject`, { review_note: note });
        this.showToast("已驳回");
        await this.loadCandidates();
      } catch (e) { this.showToast(e.message); }
    },

    /* ---------- 主动提醒 ---------- */
    async loadReminders() {
      const res = await api.get("/api/reminders" +
        (this.reminderFilter ? `?status=${this.reminderFilter}` : ""));
      this.reminders = res.items;
    },
    async scanReminders() {
      try {
        const res = await api.post("/api/reminders/scan");
        this.showToast(res.message);
        await this.loadReminders();
      } catch (e) { this.showToast(e.message); }
    },
    async doneReminder(r) {
      await api.post(`/api/reminders/${r.id}/done`);
      await this.loadReminders();
    },

    /* ---------- 会话 ---------- */
    async loadConvs() {
      const res = await api.get("/api/conversations");
      this.convs = res.items;
    },
    async viewConversation(id) {
      this.convReplay = await api.get(`/api/conversations/${id}/messages`);
    },
    async runQa(c) {
      this.qaRunning = c.id;
      try {
        const res = await api.post(`/api/qa/conversations/${c.id}`);
        c.qa = res.qa;
        this.showToast(`质检完成：${res.qa.score} 分` +
          (res.qa.issues && res.qa.issues.length ? `，发现 ${res.qa.issues.length} 个问题` : ""));
      } catch (e) {
        this.showToast(e.message);
      } finally {
        this.qaRunning = null;
      }
    },
    async downloadCsv(kind) {
      try {
        const r = await fetch(`/api/export/${kind}`,
          { headers: { Authorization: "Bearer " + api.token } });
        if (!r.ok) throw new Error(`导出失败（${r.status}）`);
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${kind}_${new Date().toISOString().slice(0, 10)}.csv`;
        a.click();
        URL.revokeObjectURL(url);
        this.showToast("已导出 CSV（Excel 可直接打开）");
      } catch (e) { this.showToast(e.message); }
    },
  },
}).mount("#app");
