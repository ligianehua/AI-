/* 客户聊天页（登录 + 通知 + 人工接管轮询） */
const { createApp } = Vue;

createApp({
  data() {
    return {
      mode: { mock: true, model: "" },
      me: null,               // 登录客户
      loginPhone: "",
      loginName: "",
      loginError: "",
      demoCustomers: [],
      conversations: [],
      conv: null,
      messages: [],
      draft: "",
      sending: false,
      showRating: false,
      ratingScore: 0,
      ratingComment: "",
      toast: "",
      notifications: [],
      notifyUnread: 0,
      showNotify: false,
      attachImage: null,   // dataURL
      quickChips: ["查询我的订单", "我要退货", "扫地机器人不开机了", "查询退换货进度", "转人工客服"],
      _key: 0,
      _lastServerMsgId: 0,
      _pollTimer: null,
      _notifyTimer: null,
    };
  },
  async mounted() {
    api.onUnauthorized = () => this.forceLogin();
    this.mode = await api.get("/api/meta/mode");
    try {
      const demo = await api.get("/api/auth/demo-accounts");
      this.demoCustomers = demo.customers || [];
    } catch (e) { /* ignore */ }

    const saved = localStorage.getItem("cust_token");
    const info = localStorage.getItem("cust_info");
    if (saved && info) {
      api.token = saved;
      this.me = JSON.parse(info);
      await this.afterLogin();
    }
    this._pollTimer = setInterval(() => this.pollActive(), 2500);
    this._notifyTimer = setInterval(() => this.loadNotifications(), 30000);
  },
  methods: {
    renderText,
    showToast(msg) {
      this.toast = msg;
      setTimeout(() => (this.toast = ""), 2500);
    },
    forceLogin() {
      api.token = null;
      this.me = null;
      localStorage.removeItem("cust_token");
      localStorage.removeItem("cust_info");
    },
    async login() {
      this.loginError = "";
      try {
        const res = await api.post("/api/auth/customer/login",
          { phone: this.loginPhone, name: this.loginName });
        api.token = res.token;
        this.me = res.customer;
        localStorage.setItem("cust_token", res.token);
        localStorage.setItem("cust_info", JSON.stringify(res.customer));
        await this.afterLogin();
      } catch (e) {
        this.loginError = e.message;
      }
    },
    async logout() {
      try { await api.post("/api/auth/logout"); } catch (e) { /* ignore */ }
      this.forceLogin();
      this.conv = null;
      this.messages = [];
      this.conversations = [];
    },
    async afterLogin() {
      await this.loadConversations();
      await this.loadNotifications();
    },
    async loadNotifications() {
      if (!this.me) return;
      try {
        const res = await api.get("/api/notifications");
        this.notifications = res.items;
        this.notifyUnread = res.unread;
      } catch (e) { /* ignore */ }
    },
    async readNotify(n) {
      await api.post(`/api/notifications/${n.id}/read`);
      await this.loadNotifications();
    },
    async loadConversations() {
      const res = await api.get("/api/conversations");
      this.conversations = res.items;
    },
    async newConversation() {
      const conv = await api.post("/api/conversations");
      await this.loadConversations();
      this.conv = this.conversations.find(c => c.id === conv.id) || conv;
      this.messages = [];
      this._lastServerMsgId = 0;
      this.pushGreeting();
    },
    pushGreeting() {
      this.messages.push({
        key: ++this._key, role: "assistant", streaming: false,
        text: `您好，${this.me.name}！我是智服小助 🤖\n请问有什么可以帮您？可以直接输入问题，或点击下方快捷入口。`,
        tool_calls: [], cards: [], time: this.nowTime(),
      });
    },
    _mapServer(rows) {
      return rows.map(m => ({
        key: "s" + m.id, id: m.id, role: m.role, text: m.text,
        agent_name: m.agent_name, streaming: false,
        image: m.image, feedback: m.feedback,
        tool_calls: (m.tool_calls || []).map(t => ({ ...t, running: false })),
        cards: [], time: m.created_at,
      }));
    },
    pickImage(ev) {
      const file = ev.target.files[0];
      ev.target.value = "";
      if (!file) return;
      if (file.size > 5 * 1024 * 1024) return this.showToast("图片超过 5MB 限制");
      const reader = new FileReader();
      reader.onload = () => (this.attachImage = reader.result);
      reader.readAsDataURL(file);
    },
    async sendFeedback(m, value) {
      if (m.feedback === value) return;
      try {
        await api.post(`/api/conversations/${this.conv.id}/messages/${m.id}/feedback`,
          { value });
        m.feedback = value;
        this.showToast(value === "up" ? "感谢您的反馈 😊"
          : "抱歉没帮到您，已记录并会持续改进；您也可以转人工客服");
      } catch (e) { this.showToast(e.message); }
    },
    async openConversation(c) {
      const res = await api.get(`/api/conversations/${c.id}/messages`);
      this.conv = res.conversation;
      this.messages = this._mapServer(res.messages);
      this._lastServerMsgId = res.messages.length
        ? res.messages[res.messages.length - 1].id : 0;
      if (!this.messages.length) this.pushGreeting();
      this.scrollBottom();
    },
    async pollActive() {
      if (!this.me || !this.conv || this.conv.status !== "active" || this.sending) return;
      try {
        const res = await api.get(`/api/conversations/${this.conv.id}/messages`);
        const rows = res.messages;
        const lastId = rows.length ? rows[rows.length - 1].id : 0;
        const modeChanged = res.conversation.mode !== this.conv.mode ||
                            res.conversation.status !== this.conv.status;
        if (lastId > this._lastServerMsgId || modeChanged) {
          this.conv = res.conversation;
          this.messages = this._mapServer(rows);
          this._lastServerMsgId = lastId;
          this.scrollBottom();
          const inList = this.conversations.find(x => x.id === this.conv.id);
          if (inList) { inList.mode = this.conv.mode; inList.status = this.conv.status; }
        }
      } catch (e) { /* ignore */ }
    },
    nowTime() {
      const d = new Date();
      return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
    },
    scrollBottom() {
      this.$nextTick(() => {
        const el = this.$refs.msgList;
        if (el) el.scrollTop = el.scrollHeight;
      });
    },
    async send(preset) {
      const text = (preset || this.draft).trim();
      const image = preset ? null : this.attachImage;
      if ((!text && !image) || this.sending || !this.conv) return;
      this.draft = "";
      this.attachImage = null;
      this.sending = true;

      this.messages.push({
        key: ++this._key, role: "user", text, image, streaming: false,
        tool_calls: [], cards: [], time: this.nowTime(),
      });
      const aiMsg = {
        key: ++this._key, role: "assistant", text: "", streaming: true,
        tool_calls: [], cards: [], time: this.nowTime(),
      };
      let humanMode = this.conv.mode === "human";
      if (!humanMode) this.messages.push(aiMsg);
      this.scrollBottom();

      try {
        await api.stream("/api/chat/stream",
          { conversation_id: this.conv.id, message: text,
            ...(image ? { image_base64: image } : {}) },
          (event, data) => {
            if (event === "meta" && data.mode === "human") {
              humanMode = true;
            } else if (event === "text_delta") {
              aiMsg.text += data.text;
            } else if (event === "tool_start") {
              aiMsg.tool_calls.push({ label: data.label, name: data.name, running: true, ok: null, summary: "" });
            } else if (event === "tool_end") {
              const t = aiMsg.tool_calls.slice().reverse()
                .find(x => x.name === data.name && x.running);
              if (t) { t.running = false; t.ok = data.ok; t.summary = data.summary; }
            } else if (event === "card") {
              aiMsg.cards.push(data);
            } else if (event === "done" && data.message_id) {
              this._lastServerMsgId = data.message_id;
              aiMsg.id = data.message_id;  // 有 id 才显示反馈按钮
            } else if (event === "error") {
              aiMsg.text += `\n⚠️ ${data.message}`;
            }
            this.scrollBottom();
          });
      } catch (e) {
        aiMsg.text += `\n⚠️ ${e.message}`;
      } finally {
        aiMsg.streaming = false;
        this.sending = false;
        this.scrollBottom();
        if (humanMode) await this.pollActiveForce();
        if (this.conv && this.conv.title === "新会话") this.loadConversations();
      }
    },
    async pollActiveForce() {
      this._lastServerMsgId = 0;  // 强制下一轮轮询重建
      await this.pollActive();
    },
    async submitRating() {
      try {
        await api.post("/api/satisfaction", {
          conversation_id: this.conv.id, score: this.ratingScore, comment: this.ratingComment,
        });
        await api.post(`/api/conversations/${this.conv.id}/close`);
        this.showToast("感谢您的评价！会话已结束");
        this.finishRating();
      } catch (e) {
        this.showToast(e.message);
      }
    },
    async closeWithoutRating() {
      try {
        await api.post(`/api/conversations/${this.conv.id}/close`);
        this.showToast("会话已结束");
        this.finishRating();
      } catch (e) {
        this.showToast(e.message);
      }
    },
    async finishRating() {
      this.showRating = false;
      this.ratingScore = 0;
      this.ratingComment = "";
      if (this.conv) this.conv.status = "closed";
      await this.loadConversations();
    },
  },
}).mount("#app");
