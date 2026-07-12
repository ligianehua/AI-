"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api, apiErrorMessage } from "@/lib/api/client";

export function NewOpportunityDialog() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [accountId, setAccountId] = useState("");
  const [name, setName] = useState("");
  const [amount, setAmount] = useState("");
  const [closeDate, setCloseDate] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const { data: accounts } = useQuery({
    queryKey: ["accounts-options"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/accounts", {
        params: { query: { page: 1, page_size: 100 } },
      });
      if (error || !data) throw new Error("加载客户失败");
      return data.items;
    },
    enabled: open,
  });

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!accountId) {
      toast.error("请选择客户");
      return;
    }
    setSubmitting(true);
    try {
      const { error } = await api.POST("/api/v1/opportunities", {
        body: {
          account_id: accountId,
          name,
          amount: amount || "0",
          expected_close_date: closeDate || null,
        },
      });
      if (error) {
        toast.error(`创建失败：${apiErrorMessage(error)}`);
        return;
      }
      toast.success("商机已创建");
      setOpen(false);
      setAccountId("");
      setName("");
      setAmount("");
      setCloseDate("");
      queryClient.invalidateQueries({ queryKey: ["kanban"] });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>新建商机</Button>
      </DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>新建商机</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-3">
          <div className="grid gap-1.5">
            <Label>客户 *</Label>
            <Select value={accountId} onValueChange={setAccountId}>
              <SelectTrigger>
                <SelectValue placeholder="选择客户" />
              </SelectTrigger>
              <SelectContent>
                {(accounts ?? []).map((a) => (
                  <SelectItem key={a.id} value={a.id}>
                    {a.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="opp_name_new">商机名称 *</Label>
            <Input
              id="opp_name_new"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="opp_amount_new">预计金额（元）</Label>
              <Input
                id="opp_amount_new"
                type="number"
                min="0"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="opp_close_date">预计成交日</Label>
              <Input
                id="opp_close_date"
                type="date"
                value={closeDate}
                onChange={(e) => setCloseDate(e.target.value)}
              />
            </div>
          </div>
          <Button type="submit" disabled={submitting}>
            {submitting ? "创建中…" : "创建"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
