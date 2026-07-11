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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api/client";
import { SOURCE_LABELS, type LeadSource } from "@/lib/leads-labels";

const EMPTY_FORM = {
  source: "website" as LeadSource,
  account_name: "",
  contact_name: "",
  contact_phone: "",
  contact_wechat: "",
  industry: "",
  requirement_desc: "",
};

export function LeadFormDialog() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);

  function set<K extends keyof typeof EMPTY_FORM>(key: K, value: (typeof EMPTY_FORM)[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const { data, error } = await api.POST("/api/v1/leads", {
        body: {
          source: form.source,
          account_name: form.account_name,
          contact_name: form.contact_name || null,
          contact_phone: form.contact_phone || null,
          contact_wechat: form.contact_wechat || null,
          industry: form.industry || null,
          requirement_desc: form.requirement_desc || null,
        },
      });
      if (error || !data) {
        toast.error("创建失败，请检查填写内容（手机号需为 11 位）");
        return;
      }
      if (data.duplicate_warnings.length > 0) {
        const w = data.duplicate_warnings[0];
        toast.warning(
          `疑似撞单：${w.matched_field === "contact_phone" ? "手机号" : "公司名"}与「${w.account_name}」（负责人：${w.owner_name}）重复，请知悉`,
          { duration: 8000 },
        );
      } else {
        toast.success("线索已创建，AI 评分进行中");
      }
      setForm(EMPTY_FORM);
      setOpen(false);
      queryClient.invalidateQueries({ queryKey: ["leads"] });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>新建线索</Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>新建线索</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="account_name">客户公司 *</Label>
              <Input
                id="account_name"
                required
                value={form.account_name}
                onChange={(e) => set("account_name", e.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <Label>来源 *</Label>
              <Select
                value={form.source}
                onValueChange={(v) => set("source", v as LeadSource)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(SOURCE_LABELS).map(([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="contact_name">联系人</Label>
              <Input
                id="contact_name"
                value={form.contact_name}
                onChange={(e) => set("contact_name", e.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="contact_phone">手机号</Label>
              <Input
                id="contact_phone"
                placeholder="13800000000"
                value={form.contact_phone}
                onChange={(e) => set("contact_phone", e.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="contact_wechat">微信</Label>
              <Input
                id="contact_wechat"
                value={form.contact_wechat}
                onChange={(e) => set("contact_wechat", e.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="industry">行业</Label>
              <Input
                id="industry"
                placeholder="如：制造业"
                value={form.industry}
                onChange={(e) => set("industry", e.target.value)}
              />
            </div>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="requirement_desc">需求描述</Label>
            <Textarea
              id="requirement_desc"
              rows={3}
              placeholder="客户想解决什么问题、预算、时间要求……"
              value={form.requirement_desc}
              onChange={(e) => set("requirement_desc", e.target.value)}
            />
          </div>
          <Button type="submit" disabled={submitting}>
            {submitting ? "创建中…" : "创建（自动 AI 评分）"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
