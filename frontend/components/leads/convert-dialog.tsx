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
import { api, apiErrorMessage } from "@/lib/api/client";
import type { LeadOut } from "@/lib/hooks/use-leads";

function ConvertForm({ lead, onClose }: { lead: LeadOut; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [opportunityName, setOpportunityName] = useState(`${lead.account_name}-初始商机`);
  const [amount, setAmount] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const { error } = await api.POST("/api/v1/leads/{lead_id}/convert", {
        params: { path: { lead_id: lead.id } },
        body: {
          opportunity_name: opportunityName || null,
          amount: amount ? amount : null,
        },
      });
      if (error) {
        toast.error(`转化失败：${apiErrorMessage(error)}`);
        return;
      }
      toast.success("已转化：客户、联系人、商机已创建");
      onClose();
      queryClient.invalidateQueries({ queryKey: ["leads"] });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="grid gap-3">
      <div className="grid gap-1.5">
        <Label htmlFor="opp_name">商机名称</Label>
        <Input
          id="opp_name"
          value={opportunityName}
          onChange={(e) => setOpportunityName(e.target.value)}
        />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="opp_amount">预计金额（元，可留空）</Label>
        <Input
          id="opp_amount"
          type="number"
          min="0"
          step="1000"
          placeholder="如 200000"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
      </div>
      <Button type="submit" disabled={submitting}>
        {submitting ? "转化中…" : "确认转化"}
      </Button>
    </form>
  );
}

export function ConvertDialog({
  lead,
  onClose,
}: {
  lead: LeadOut | null;
  onClose: () => void;
}) {
  return (
    <Dialog open={lead !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>转化线索：{lead?.account_name}</DialogTitle>
          <DialogDescription>
            将创建客户、联系人和初始商机（同一事务，失败自动回滚）
          </DialogDescription>
        </DialogHeader>
        {lead && <ConvertForm key={lead.id} lead={lead} onClose={onClose} />}
      </DialogContent>
    </Dialog>
  );
}
