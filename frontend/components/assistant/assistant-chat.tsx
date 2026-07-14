"use client";

import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { streamSSE } from "@/lib/api/sse";
import { cn } from "@/lib/utils";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  tools: string[]; // 助手消息：本轮调用过的工具提示（如"正在查询商机…"）
  error?: string;
}

const QUICK_QUESTIONS = [
  "我手上哪个商机风险最大？",
  "评分最高的线索有哪些？",
  "还没联系的新线索有哪些？",
  "客户嫌贵怎么回？",
];

export function AssistantChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send(question: string) {
    const message = question.trim();
    if (!message || sending) return;
    setSending(true);
    setInput("");

    // 回传给后端的历史：此前所有完成的消息（后端截取最近 10 条）
    const history = messages
      .filter((m) => m.content && !m.error)
      .map((m) => ({ role: m.role, content: m.content }));

    setMessages((prev) => [
      ...prev,
      { role: "user", content: message, tools: [] },
      { role: "assistant", content: "", tools: [] },
    ]);

    const patchLast = (patch: (m: ChatMessage) => ChatMessage) =>
      setMessages((prev) => [...prev.slice(0, -1), patch(prev[prev.length - 1])]);

    abortRef.current = new AbortController();
    try {
      await streamSSE(
        "/api/v1/assistant/chat",
        { message, history },
        (event, data) => {
          if (event === "tool") {
            patchLast((m) => ({ ...m, tools: [...m.tools, String(data.label ?? "正在查询…")] }));
          } else if (event === "delta") {
            patchLast((m) => ({ ...m, content: m.content + String(data.text ?? "") }));
          } else if (event === "error") {
            patchLast((m) => ({ ...m, error: String(data.message ?? "助手出错了") }));
          }
        },
        abortRef.current.signal,
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : "发送失败";
      toast.error(msg);
      patchLast((m) => ({ ...m, error: m.error ?? msg }));
    } finally {
      setSending(false);
    }
  }

  return (
    <Card>
      <CardContent className="space-y-4 pt-6">
        <div className="max-h-[52vh] min-h-48 space-y-3 overflow-y-auto pr-1">
          {messages.length === 0 && (
            <div className="py-8 text-center text-sm text-muted-foreground">
              <p className="mb-3">试试这些问题：</p>
              <div className="flex flex-wrap justify-center gap-2">
                {QUICK_QUESTIONS.map((q) => (
                  <Button key={q} variant="outline" size="sm" onClick={() => send(q)}>
                    {q}
                  </Button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
              <div
                className={cn(
                  "max-w-[85%] rounded-lg px-3 py-2 text-sm",
                  m.role === "user" ? "bg-primary text-primary-foreground" : "border bg-muted/40",
                )}
              >
                {m.tools.length > 0 && (
                  <div className="mb-1 space-y-0.5">
                    {m.tools.map((t, j) => (
                      <p key={j} className="text-xs text-muted-foreground">
                        🔍 {t}
                      </p>
                    ))}
                  </div>
                )}
                {m.content && <p className="whitespace-pre-wrap">{m.content}</p>}
                {m.error && <p className="text-destructive">{m.error}</p>}
                {m.role === "assistant" && !m.content && !m.error && (
                  <p className="animate-pulse text-muted-foreground">
                    {m.tools.length > 0 ? "正在整理答案…" : "思考中…"}
                  </p>
                )}
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
        >
          <Input
            placeholder="问点什么，比如：这周该优先跟进谁？"
            value={input}
            maxLength={2000}
            onChange={(e) => setInput(e.target.value)}
            disabled={sending}
          />
          <Button type="submit" disabled={sending || !input.trim()}>
            {sending ? "回答中…" : "发送"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
