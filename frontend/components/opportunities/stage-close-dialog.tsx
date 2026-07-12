"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api, apiErrorMessage } from "@/lib/api/client";
import type { OpportunityOut, OpportunityStage } from "@/lib/opportunity-labels";

export interface StageCloseTarget {
  opportunity: OpportunityOut;
  stage: Extract<OpportunityStage, "won" | "lost">;
}

function CloseForm({ target, onClose }: { target: StageCloseTarget; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [amount, setAmount] = useState(String(target.opportunity.amount ?? ""));
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const isWon = target.stage === "won";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const { error } = await api.PATCH("/api/v1/opportunities/{opportunity_id}/stage", {
        params: { path: { opportunity_id: target.opportunity.id } },
        body: {
          stage: target.stage,
          amount: isWon ? amount : null,
          lost_reason: isWon ? null : reason,
        },
      });
      if (error) {
        toast.error(`操作失败：${apiErrorMessage(error)}`);
        return;
      }
      toast.success(isWon ? "已标记赢单 🎉" : "已标记输单");
      onClose();
      queryClient.invalidateQueries({ queryKey: ["kanban"] });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="grid gap-3">
      {isWon ? (
        <div className="grid gap-1.5">
          <Label htmlFor="won_amount">成交金额（元）*</Label>
          <Input
            id="won_amount"
            type="number"
            min="0"
            required
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </div>
      ) : (
        <div className="grid gap-1.5">
          <Label htmlFor="lost_reason">输单原因 *</Label>
          <Textarea
            id="lost_reason"
            required
            rows={3}
            placeholder="如：预算削减 / 选择竞品 / 需求取消……"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </div>
      )}
      <Button type="submit" disabled={submitting}>
        {submitting ? "提交中…" : isWon ? "确认赢单" : "确认输单"}
      </Button>
    </form>
  );
}

export function StageCloseDialog({
  target,
  onClose,
}: {
  target: StageCloseTarget | null;
  onClose: () => void;
}) {
  return (
    <Dialog open={target !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>
            {target?.stage === "won" ? "赢单确认" : "输单确认"}：{target?.opportunity.name}
          </DialogTitle>
          <DialogDescription>
            {target?.stage === "won"
              ? "请确认最终成交金额（预测与业绩的数据原料）"
              : "原因是未来归因分析的数据原料，请如实填写"}
          </DialogDescription>
        </DialogHeader>
        {target && (
          <CloseForm key={target.opportunity.id + target.stage} target={target} onClose={onClose} />
        )}
      </DialogContent>
    </Dialog>
  );
}
