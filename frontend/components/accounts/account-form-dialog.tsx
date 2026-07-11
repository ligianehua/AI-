"use client";

import { useQueryClient } from "@tanstack/react-query";
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
import { Textarea } from "@/components/ui/textarea";
import { api, apiErrorMessage } from "@/lib/api/client";

const EMPTY = { name: "", industry: "", size: "", region: "", website: "", remark: "" };

export function AccountFormDialog() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [submitting, setSubmitting] = useState(false);

  function set<K extends keyof typeof EMPTY>(key: K, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const { error } = await api.POST("/api/v1/accounts", {
        body: {
          name: form.name,
          industry: form.industry || null,
          size: form.size || null,
          region: form.region || null,
          website: form.website || null,
          remark: form.remark || null,
        },
      });
      if (error) {
        toast.error(`创建失败：${apiErrorMessage(error)}`);
        return;
      }
      toast.success("客户已创建");
      setForm(EMPTY);
      setOpen(false);
      queryClient.invalidateQueries({ queryKey: ["accounts"] });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>新建客户</Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>新建客户</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="acc_name">公司名称 *</Label>
              <Input
                id="acc_name"
                required
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="acc_industry">行业</Label>
              <Input
                id="acc_industry"
                value={form.industry}
                onChange={(e) => set("industry", e.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="acc_size">规模</Label>
              <Input
                id="acc_size"
                placeholder="如 201-500人"
                value={form.size}
                onChange={(e) => set("size", e.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="acc_region">地区</Label>
              <Input
                id="acc_region"
                value={form.region}
                onChange={(e) => set("region", e.target.value)}
              />
            </div>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="acc_remark">备注</Label>
            <Textarea
              id="acc_remark"
              rows={2}
              value={form.remark}
              onChange={(e) => set("remark", e.target.value)}
            />
          </div>
          <Button type="submit" disabled={submitting}>
            {submitting ? "创建中…" : "创建"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
