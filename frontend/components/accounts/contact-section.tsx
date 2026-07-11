"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import type { components } from "@/lib/api/schema";

type Contact = components["schemas"]["ContactOut"];
type RoleInDeal = components["schemas"]["ContactRoleInDeal"];

const ROLE_LABELS: Record<RoleInDeal, string> = {
  decision_maker: "决策人",
  influencer: "影响者",
  user: "使用者",
  gatekeeper: "守门人",
};

function AddContactDialog({ accountId }: { accountId: string }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", title: "", phone: "", role: "" });
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const { error } = await api.POST("/api/v1/contacts", {
        body: {
          account_id: accountId,
          name: form.name,
          title: form.title || null,
          phone: form.phone || null,
          role_in_deal: (form.role || null) as RoleInDeal | null,
        },
      });
      if (error) {
        toast.error(`添加失败：${apiErrorMessage(error)}`);
        return;
      }
      toast.success("联系人已添加");
      setForm({ name: "", title: "", phone: "", role: "" });
      setOpen(false);
      queryClient.invalidateQueries({ queryKey: ["account"] });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline">
          添加联系人
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>添加联系人</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="c_name">姓名 *</Label>
            <Input
              id="c_name"
              required
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="c_title">职位</Label>
            <Input
              id="c_title"
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="c_phone">电话</Label>
            <Input
              id="c_phone"
              value={form.phone}
              onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
            />
          </div>
          <div className="grid gap-1.5">
            <Label>决策角色</Label>
            <Select
              value={form.role}
              onValueChange={(v) => setForm((f) => ({ ...f, role: v }))}
            >
              <SelectTrigger>
                <SelectValue placeholder="选择角色（可选）" />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(ROLE_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button type="submit" disabled={submitting}>
            {submitting ? "添加中…" : "添加"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function ContactSection({
  accountId,
  contacts,
}: {
  accountId: string;
  contacts: Contact[];
}) {
  const queryClient = useQueryClient();

  async function handleDelete(contact: Contact) {
    const { error } = await api.DELETE("/api/v1/contacts/{contact_id}", {
      params: { path: { contact_id: contact.id } },
    });
    if (error) {
      toast.error("删除失败");
      return;
    }
    toast.success(`已删除联系人：${contact.name}`);
    queryClient.invalidateQueries({ queryKey: ["account"] });
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>联系人（{contacts.length}）</CardTitle>
        <AddContactDialog accountId={accountId} />
      </CardHeader>
      <CardContent>
        {contacts.length === 0 ? (
          <p className="text-sm text-muted-foreground">暂无联系人</p>
        ) : (
          <ul className="space-y-2">
            {contacts.map((c) => (
              <li key={c.id} className="flex items-center gap-2 text-sm">
                <span className="font-medium">{c.name}</span>
                {c.title && <span className="text-muted-foreground">{c.title}</span>}
                {c.role_in_deal && (
                  <Badge variant="secondary">{ROLE_LABELS[c.role_in_deal]}</Badge>
                )}
                {c.phone && <span className="text-muted-foreground">{c.phone}</span>}
                <Button
                  variant="ghost"
                  size="sm"
                  className="ml-auto h-6 px-2 text-xs text-muted-foreground"
                  onClick={() => handleDelete(c)}
                >
                  删除
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
