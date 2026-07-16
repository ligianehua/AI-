/* API 封装：fetch + token 鉴权 + SSE 流解析 */
const api = {
  token: null,           // 页面初始化时从 localStorage 注入
  onUnauthorized: null,  // 401 回调（弹登录框）

  _headers(json = true) {
    const h = {};
    if (json) h["Content-Type"] = "application/json";
    if (this.token) h["Authorization"] = "Bearer " + this.token;
    return h;
  },
  async _handle(r) {
    if (r.status === 401 && this.onUnauthorized) this.onUnauthorized();
    if (!r.ok) throw await this._err(r);
    return r.json();
  },
  async get(url) {
    return this._handle(await fetch(url, { headers: this._headers(false) }));
  },
  async post(url, body) {
    return this._handle(await fetch(url, {
      method: "POST", headers: this._headers(),
      body: body != null ? JSON.stringify(body) : null,
    }));
  },
  async put(url, body) {
    return this._handle(await fetch(url, {
      method: "PUT", headers: this._headers(), body: JSON.stringify(body),
    }));
  },
  async patch(url, body) {
    return this._handle(await fetch(url, {
      method: "PATCH", headers: this._headers(), body: JSON.stringify(body),
    }));
  },
  async del(url) {
    return this._handle(await fetch(url, { method: "DELETE", headers: this._headers(false) }));
  },
  async upload(url, formData) {
    return this._handle(await fetch(url, {
      method: "POST", headers: this._headers(false), body: formData,
    }));
  },
  async _err(r) {
    let msg = `请求失败（${r.status}）`;
    try {
      const data = await r.json();
      if (data.detail) msg = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch (e) { /* ignore */ }
    const err = new Error(msg);
    err.status = r.status;
    return err;
  },

  /* POST + SSE 流（EventSource 不支持 POST，用 fetch 读 ReadableStream） */
  async stream(url, body, onEvent) {
    const r = await fetch(url, {
      method: "POST", headers: this._headers(), body: JSON.stringify(body),
    });
    if (r.status === 401 && this.onUnauthorized) this.onUnauthorized();
    if (!r.ok) throw await this._err(r);
    const reader = r.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buffer.indexOf("\n\n")) >= 0) {
        const chunk = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        let event = "message", data = "";
        for (const line of chunk.split("\n")) {
          if (line.startsWith("event: ")) event = line.slice(7).trim();
          else if (line.startsWith("data: ")) data += line.slice(6);
        }
        if (data) {
          try { onEvent(event, JSON.parse(data)); }
          catch (e) { console.warn("SSE parse error", e, data); }
        }
      }
    }
  },
};

/* 极简 markdown 渲染：转义 + **加粗** + 换行 */
function renderText(text) {
  if (!text) return "";
  const esc = text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  return esc.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}
