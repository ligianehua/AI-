"use client";

import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api/client";
import { streamSSE } from "@/lib/api/sse";
import { CATEGORY_LABELS, CHANNEL_LABELS, type ScriptCategory } from "@/lib/script-labels";

interface SourceInfo {
  no_reference: boolean;
  scripts: { id: string; scenario: string; preview: string }[];
  knowledge: { doc_title: string; preview: string }[];
}

export function RecommendPanel() {
  const [scenario, setScenario] = useState<ScriptCategory>("objection");
  const [channel, setChannel] = useState("wechat");
  const [accountId, setAccountId] = useState<string>("none");
  const [hint, setHint] = useState("");
  const [generating, setGenerating] = useState(false);
  const [text, setText] = useState("");
  const [sources, setSources] = useState<SourceInfo | null>(null);
  const [llmCallId, setLlmCallId] = useState<string | null>(null);
  const [feedbackSent, setFeedbackSent] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const { data: accounts } = useQuery({
    queryKey: ["accounts-options"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/accounts", {
        params: { query: { page: 1, page_size: 100 } },
      });
      if (error || !data) throw new Error("加载客户失败");
      return data.items;
    },
  });

  async function handleGenerate() {
    setGenerating(true);
    setText("");
    setSources(null);
    setLlmCallId(null);
    setFeedbackSent(null);
    abortRef.current = new AbortController();
    try {
      await streamSSE(
        "/api/v1/scripts/recommend",
        {
          scenario,
          channel,
          account_id: accountId !== "none" ? accountId : null,
          user_hint: hint || null,
        },
        (event, data) => {
          if (event === "sources") {
            setSources(data as unknown as SourceInfo);
          } else if (event === "delta") {
            setText((t) => t + (data.text as string));
          } else if (event === "done") {
            setLlmCallId((data.llm_call_id as string) ?? null);
          } else if (event === "error") {
            toast.error(String(data.message ?? "生成失败"));
          }
        },
        abortRef.current.signal,
      );
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "生成失败");
    } finally {
      setGenerating(false);
    }
  }

  async function handleFeedback(value: 1 | -1) {
    if (!llmCallId) return;
    const { error } = await api.POST("/api/v1/ai/feedback", {
      body: { llm_call_id: llmCallId, feedback: value },
    });
    if (error) {
      toast.error("反馈提交失败");
      return;
    }
    setFeedbackSent(value);
    toast.success(value === 1 ? "感谢反馈 👍" : "已记录，我们会改进 👌");
  }

  function copyText(content: string) {
    navigator.clipboard.writeText(content.trim());
    toast.success("已复制到剪贴板");
  }

  const candidates = text
    .split(/【候选\d】/)
    .map((c) => c.trim())
    .filter(Boolean);

  return (
    <Card>
      <CardHeader>
        <CardTitle>智能话术推荐</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-4">
          <div className="grid gap-1.5">
            <Label>场景</Label>
            <Select value={scenario} onValueChange={(v) => setScenario(v as ScriptCategory)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label>渠道</Label>
            <Select value={channel} onValueChange={setChannel}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(CHANNEL_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label>客户（可选，带入画像与跟进）</Label>
            <Select value={accountId} onValueChange={setAccountId}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">不指定</SelectItem>
                {(accounts ?? []).map((a) => (
                  <SelectItem key={a.id} value={a.id}>
                    {a.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label>补充提示（可选）</Label>
            <Input
              placeholder="如：客户嫌贵，预算 10 万"
              value={hint}
              onChange={(e) => setHint(e.target.value)}
            />
          </div>
        </div>
        <Button onClick={handleGenerate} disabled={generating}>
          {generating ? "生成中…" : "生成 3 条话术"}
        </Button>

        {sources && (
          <div className="rounded-md border bg-muted/40 px-3 py-2 text-sm">
            {sources.no_reference ? (
              <p className="text-amber-600">库内无匹配参考话术，以下为纯 AI 生成，请谨慎甄别</p>
            ) : (
              <div>
                <p className="mb-1 font-medium">参考了 {sources.scripts.length} 条库内话术：</p>
                <ul className="space-y-0.5 text-muted-foreground">
                  {sources.scripts.map((s) => (
                    <li key={s.id} className="truncate">
                      <Badge variant="outline" className="mr-1">
                        {s.scenario}
                      </Badge>
                      {s.preview}…
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {sources.knowledge.length > 0 && (
              <p className="mt-1 text-muted-foreground">
                知识参考：{sources.knowledge.map((k) => k.doc_title).join("、")}
              </p>
            )}
          </div>
        )}

        {candidates.length > 0 && (
          <div className="space-y-3">
            {candidates.map((candidate, i) => (
              <div key={i} className="rounded-md border p-3">
                <div className="mb-1 flex items-center justify-between">
                  <Badge variant="secondary">候选 {i + 1}</Badge>
                  <Button variant="ghost" size="sm" onClick={() => copyText(candidate)}>
                    复制
                  </Button>
                </div>
                <p className="text-sm whitespace-pre-wrap">{candidate}</p>
              </div>
            ))}
          </div>
        )}
        {generating && text === "" && (
          <p className="text-sm text-muted-foreground">AI 正在检索话术库并生成…</p>
        )}

        {llmCallId && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <span>这次推荐有帮助吗？</span>
            <Button
              variant={feedbackSent === 1 ? "default" : "outline"}
              size="sm"
              disabled={feedbackSent !== null}
              onClick={() => handleFeedback(1)}
            >
              👍 有用
            </Button>
            <Button
              variant={feedbackSent === -1 ? "default" : "outline"}
              size="sm"
              disabled={feedbackSent !== null}
              onClick={() => handleFeedback(-1)}
            >
              👎 不行
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
