"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { formatDate } from "@/lib/datetime";
import { api, apiErrorMessage } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import {
  formatWan,
  SCENARIO_LABELS,
  STAGE_LABELS,
  type OpportunityOut,
} from "@/lib/opportunity-labels";

type ActivityType = components["schemas"]["ActivityType"];

const ACTIVITY_TYPE_LABELS: Record<ActivityType, string> = {
  call: "电话",
  visit: "拜访",
  wechat: "微信",
  email: "邮件",
  meeting: "会议",
  other: "其他",
};

interface NextActionItem {
  action: string;
  reason: string;
  suggested_script_scenario: string | null;
}

function ActivitySection({ opportunityId }: { opportunityId: string }) {
  const queryClient = useQueryClient();
  const [type, setType] = useState<ActivityType>("call");
  const [content, setContent] = useState("");
  const [nextAction, setNextAction] = useState("");
  const [nextDate, setNextDate] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const { data: activities } = useQuery({
    queryKey: ["opp-activities", opportunityId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/activities", {
        params: {
          query: { related_type: "opportunity", related_id: opportunityId },
        },
      });
      if (error || !data) throw new Error("加载跟进失败");
      return data;
    },
  });

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const { error } = await api.POST("/api/v1/activities", {
        body: {
          related_type: "opportunity",
          related_id: opportunityId,
          type,
          content,
          next_action: nextAction || null,
          next_action_date: nextDate || null,
        },
      });
      if (error) {
        toast.error(`添加失败：${apiErrorMessage(error)}`);
        return;
      }
      toast.success("跟进已记录");
      setContent("");
      setNextAction("");
      setNextDate("");
      queryClient.invalidateQueries({ queryKey: ["opp-activities", opportunityId] });
      queryClient.invalidateQueries({ queryKey: ["kanban"] });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-3">
      <form onSubmit={handleAdd} className="space-y-2 rounded-md border p-3">
        <div className="flex gap-2">
          <Select value={type} onValueChange={(v) => setType(v as ActivityType)}>
            <SelectTrigger className="w-24">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(ACTIVITY_TYPE_LABELS).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Textarea
            required
            rows={1}
            placeholder="跟进内容…"
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="min-h-9 flex-1"
          />
        </div>
        <div className="flex gap-2">
          <Input
            placeholder="下一步行动（可选）"
            value={nextAction}
            onChange={(e) => setNextAction(e.target.value)}
          />
          <Input
            type="date"
            value={nextDate}
            onChange={(e) => setNextDate(e.target.value)}
            className="w-40"
          />
          <Button type="submit" size="sm" disabled={submitting}>
            记录
          </Button>
        </div>
      </form>
      <ul className="max-h-48 space-y-2 overflow-y-auto text-sm">
        {(activities ?? []).map((a) => (
          <li key={a.id} className="rounded-md bg-muted/50 px-3 py-2">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>{formatDate(a.created_at)}</span>
              <Badge variant="outline">{ACTIVITY_TYPE_LABELS[a.type]}</Badge>
              <span>{a.owner_name}</span>
            </div>
            <p className="mt-1">{a.content}</p>
            {a.next_action && (
              <p className="text-xs text-muted-foreground">
                下一步：{a.next_action}
                {a.next_action_date && `（${a.next_action_date}）`}
              </p>
            )}
          </li>
        ))}
        {activities?.length === 0 && (
          <li className="text-muted-foreground">暂无跟进记录</li>
        )}
      </ul>
    </div>
  );
}

function NextActionsSection({ opportunityId }: { opportunityId: string }) {
  const queryClient = useQueryClient();
  const [actions, setActions] = useState<NextActionItem[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [savedIdx, setSavedIdx] = useState<Set<number>>(new Set());

  async function handleLoad() {
    setLoading(true);
    try {
      const { data, error } = await api.GET(
        "/api/v1/opportunities/{opportunity_id}/next-actions",
        { params: { path: { opportunity_id: opportunityId } } },
      );
      if (error || !data) {
        toast.error(`AI 建议获取失败：${apiErrorMessage(error, "AI 服务暂不可用")}`);
        return;
      }
      setActions(data.actions as unknown as NextActionItem[]);
      setSavedIdx(new Set());
    } catch {
      toast.error("网络异常，请重试");
    } finally {
      setLoading(false);
    }
  }

  async function handleToTodo(action: NextActionItem, index: number) {
    // 一键转任务（PLAN §6.3）：以明天为期限记入跟进计划，进入今日待办/风险扫描体系
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowStr = tomorrow.toISOString().slice(0, 10);
    try {
      const { error } = await api.POST("/api/v1/activities", {
        body: {
          related_type: "opportunity",
          related_id: opportunityId,
          type: "other",
          content: `[AI 建议转任务] ${action.reason}`,
          next_action: action.action,
          next_action_date: tomorrowStr,
        },
      });
      if (error) {
        toast.error(`转任务失败：${apiErrorMessage(error)}`);
        return;
      }
      toast.success("已转为待办（期限：明天）");
      setSavedIdx((prev) => new Set(prev).add(index));
      queryClient.invalidateQueries({ queryKey: ["opp-activities", opportunityId] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
    } catch {
      toast.error("网络异常，请重试");
    }
  }

  return (
    <div className="space-y-2">
      <Button variant="outline" size="sm" onClick={handleLoad} disabled={loading}>
        {loading ? "AI 分析中…" : actions ? "重新生成建议" : "AI 下一步建议"}
      </Button>
      {actions && (
        <ol className="space-y-2 text-sm">
          {actions.map((a, i) => (
            <li key={i} className="rounded-md border px-3 py-2">
              <div className="flex items-start justify-between gap-2">
                <p className="font-medium">
                  {i + 1}. {a.action}
                  {a.suggested_script_scenario && (
                    <Badge variant="secondary" className="ml-2">
                      话术：
                      {SCENARIO_LABELS[a.suggested_script_scenario] ?? a.suggested_script_scenario}
                    </Badge>
                  )}
                </p>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 shrink-0 px-2 text-xs"
                  disabled={savedIdx.has(i)}
                  onClick={() => handleToTodo(a, i)}
                >
                  {savedIdx.has(i) ? "已转待办" : "转待办"}
                </Button>
              </div>
              <p className="text-muted-foreground">{a.reason}</p>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

export function OpportunityDetailDialog({
  opportunity,
  onClose,
}: {
  opportunity: OpportunityOut | null;
  onClose: () => void;
}) {
  return (
    <Dialog open={opportunity !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{opportunity?.name}</DialogTitle>
        </DialogHeader>
        {opportunity && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <Badge>{STAGE_LABELS[opportunity.stage]}</Badge>
              <span>{opportunity.account_name}</span>
              <span>·</span>
              <span>{formatWan(Number(opportunity.amount))}</span>
              <span>·</span>
              <span>概率 {opportunity.probability}%</span>
              <span>·</span>
              <span>负责人 {opportunity.owner_name}</span>
              {opportunity.stuck_days > 7 && (
                <Badge variant="destructive">停滞 {opportunity.stuck_days} 天</Badge>
              )}
            </div>
            {opportunity.lost_reason && (
              <p className="rounded-md bg-muted px-3 py-2 text-sm">
                输单原因:{opportunity.lost_reason}
              </p>
            )}
            <NextActionsSection opportunityId={opportunity.id} />
            <ActivitySection opportunityId={opportunity.id} />
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
