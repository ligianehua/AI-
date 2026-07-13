"use client";

import { formatDateTime } from "@/lib/datetime";

import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { LeadOut } from "@/lib/hooks/use-leads";
import { URGENCY_LABELS } from "@/lib/leads-labels";

interface ScoreDetail {
  rule_score?: number;
  rule_breakdown?: Record<string, number>;
  llm_score?: number | null;
  llm?: {
    intent_score: number;
    budget_signal: boolean;
    urgency: string;
    reasons: string[];
  } | null;
  note?: string | null;
  scored_at?: string;
}

export function ScoreDetailDialog({
  lead,
  onClose,
}: {
  lead: LeadOut | null;
  onClose: () => void;
}) {
  const detail = (lead?.score_detail ?? null) as ScoreDetail | null;
  return (
    <Dialog open={lead !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>
            评分理由：{lead?.account_name}
            <Badge variant="secondary" className="ml-2">
              参考分 {lead?.score ?? "-"}
            </Badge>
          </DialogTitle>
          <DialogDescription>
            冷启动阶段为「专家规则 + 语义判断」参考分，仅供排序参考
          </DialogDescription>
        </DialogHeader>
        {detail ? (
          <div className="space-y-4 text-sm">
            <section>
              <h4 className="mb-1 font-medium">规则得分：{detail.rule_score ?? 0} / 40</h4>
              <ul className="space-y-0.5 text-muted-foreground">
                {Object.entries(detail.rule_breakdown ?? {}).map(([k, v]) => (
                  <li key={k}>
                    {k}：+{v}
                  </li>
                ))}
              </ul>
            </section>
            <section>
              <h4 className="mb-1 font-medium">
                AI 语义得分：{detail.llm_score ?? "—"} / 60
              </h4>
              {detail.llm ? (
                <div className="space-y-1 text-muted-foreground">
                  <p>
                    意向 {detail.llm.intent_score}/40 · 预算信号{" "}
                    {detail.llm.budget_signal ? "有" : "无"} · 紧迫度{" "}
                    {URGENCY_LABELS[detail.llm.urgency] ?? detail.llm.urgency}
                  </p>
                  <ul className="list-disc pl-5">
                    {detail.llm.reasons.map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                </div>
              ) : (
                <p className="text-muted-foreground">{detail.note ?? "暂无 AI 评分"}</p>
              )}
            </section>
            {detail.scored_at && (
              <p className="text-xs text-muted-foreground">
                评分时间：{formatDateTime(detail.scored_at)}
              </p>
            )}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">尚未评分</p>
        )}
      </DialogContent>
    </Dialog>
  );
}
