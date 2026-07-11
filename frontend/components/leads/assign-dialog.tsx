"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api, apiErrorMessage } from "@/lib/api/client";

export function AssignDialog({
  leadIds,
  open,
  onClose,
  onAssigned,
}: {
  leadIds: string[];
  open: boolean;
  onClose: () => void;
  onAssigned: () => void;
}) {
  const queryClient = useQueryClient();
  const [ownerId, setOwnerId] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);

  const { data: users } = useQuery({
    queryKey: ["assignable-users"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/users/assignable");
      if (error || !data) throw new Error("加载成员失败");
      return data;
    },
    enabled: open,
  });

  async function handleSubmit() {
    if (!ownerId) {
      toast.error("请选择负责人");
      return;
    }
    setSubmitting(true);
    try {
      const { data, error } = await api.POST("/api/v1/leads/assign", {
        body: { lead_ids: leadIds, owner_id: ownerId },
      });
      if (error || !data) {
        toast.error(`分配失败：${apiErrorMessage(error)}`);
        return;
      }
      toast.success(`已分配 ${data.assigned} 条线索`);
      onAssigned();
      onClose();
      queryClient.invalidateQueries({ queryKey: ["leads"] });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>批量分配（{leadIds.length} 条）</DialogTitle>
          <DialogDescription>manager 只能分配给本团队成员</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <Select value={ownerId} onValueChange={setOwnerId}>
            <SelectTrigger>
              <SelectValue placeholder="选择负责人" />
            </SelectTrigger>
            <SelectContent>
              {(users ?? []).map((u) => (
                <SelectItem key={u.id} value={u.id}>
                  {u.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button onClick={handleSubmit} disabled={submitting}>
            {submitting ? "分配中…" : "确认分配"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
