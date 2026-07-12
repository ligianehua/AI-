"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, apiErrorMessage } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { useMe } from "@/lib/hooks/use-me";

type UserOut = components["schemas"]["UserOut"];
type TeamOut = components["schemas"]["TeamOut"];
type Role = components["schemas"]["Role"];

const ROLE_LABELS: Record<Role, string> = {
  sales: "销售",
  manager: "主管",
  admin: "管理员",
};

function useTeams() {
  return useQuery({
    queryKey: ["teams"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/teams", {
        params: { query: { page: 1, page_size: 100 } },
      });
      if (error || !data) throw new Error("加载团队失败");
      return data.items;
    },
  });
}

function UserFormDialog({
  user,
  teams,
  trigger,
}: {
  user: UserOut | null; // null = 新建
  teams: TeamOut[];
  trigger: React.ReactNode;
}) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(user?.name ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>(user?.role ?? "sales");
  const [teamId, setTeamId] = useState<string>(user?.team_id ?? "none");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      if (user === null) {
        const { error } = await api.POST("/api/v1/users", {
          body: {
            name,
            email,
            password,
            role,
            team_id: teamId !== "none" ? teamId : null,
          },
        });
        if (error) {
          toast.error(`创建失败：${apiErrorMessage(error)}`);
          return;
        }
        toast.success("用户已创建");
      } else {
        const { error } = await api.PATCH("/api/v1/users/{user_id}", {
          params: { path: { user_id: user.id } },
          body: {
            name,
            role,
            team_id: teamId !== "none" ? teamId : null,
            ...(password ? { password } : {}),
          },
        });
        if (error) {
          toast.error(`保存失败：${apiErrorMessage(error)}`);
          return;
        }
        toast.success("已保存");
      }
      setOpen(false);
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{user ? `编辑：${user.name}` : "新建用户"}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="u_name">姓名 *</Label>
            <Input id="u_name" required value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          {user === null && (
            <div className="grid gap-1.5">
              <Label htmlFor="u_email">邮箱 *</Label>
              <Input
                id="u_email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
          )}
          <div className="grid gap-1.5">
            <Label htmlFor="u_password">{user ? "重置密码（留空不改）" : "密码 *（≥8 位）"}</Label>
            <Input
              id="u_password"
              type="password"
              required={user === null}
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label>角色</Label>
              <Select value={role} onValueChange={(v) => setRole(v as Role)}>
                <SelectTrigger>
                  <SelectValue />
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
            <div className="grid gap-1.5">
              <Label>团队</Label>
              <Select value={teamId} onValueChange={setTeamId}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">无团队</SelectItem>
                  {teams.map((t) => (
                    <SelectItem key={t.id} value={t.id}>
                      {t.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <Button type="submit" disabled={submitting}>
            {submitting ? "保存中…" : "保存"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function UsersSection({ teams }: { teams: TeamOut[] }) {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["admin-users"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/users", {
        params: { query: { page: 1, page_size: 100 } },
      });
      if (error || !data) throw new Error("加载用户失败");
      return data;
    },
  });
  const teamName = (id: string | null) => teams.find((t) => t.id === id)?.name ?? "—";

  async function toggleActive(user: UserOut) {
    const { error } = await api.PATCH("/api/v1/users/{user_id}", {
      params: { path: { user_id: user.id } },
      body: { is_active: !user.is_active },
    });
    if (error) {
      toast.error(apiErrorMessage(error));
      return;
    }
    queryClient.invalidateQueries({ queryKey: ["admin-users"] });
  }

  async function remove(user: UserOut) {
    const { error } = await api.DELETE("/api/v1/users/{user_id}", {
      params: { path: { user_id: user.id } },
    });
    if (error) {
      toast.error(`删除失败：${apiErrorMessage(error)}`);
      return;
    }
    toast.success(`已删除 ${user.name}`);
    queryClient.invalidateQueries({ queryKey: ["admin-users"] });
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>用户（{data?.total ?? 0}）</CardTitle>
        <UserFormDialog user={null} teams={teams} trigger={<Button size="sm">新建用户</Button>} />
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>姓名</TableHead>
              <TableHead>邮箱</TableHead>
              <TableHead>角色</TableHead>
              <TableHead>团队</TableHead>
              <TableHead>状态</TableHead>
              <TableHead className="text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(data?.items ?? []).map((u) => (
              <TableRow key={u.id}>
                <TableCell className="font-medium">{u.name}</TableCell>
                <TableCell>{u.email}</TableCell>
                <TableCell>
                  <Badge variant={u.role === "admin" ? "default" : "secondary"}>
                    {ROLE_LABELS[u.role]}
                  </Badge>
                </TableCell>
                <TableCell>{teamName(u.team_id)}</TableCell>
                <TableCell>
                  {u.is_active ? (
                    <Badge variant="outline">在职</Badge>
                  ) : (
                    <Badge variant="destructive">停用</Badge>
                  )}
                </TableCell>
                <TableCell className="space-x-1 text-right">
                  <UserFormDialog
                    user={u}
                    teams={teams}
                    trigger={
                      <Button variant="ghost" size="sm">
                        编辑
                      </Button>
                    }
                  />
                  <Button variant="ghost" size="sm" onClick={() => toggleActive(u)}>
                    {u.is_active ? "停用" : "启用"}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive"
                    onClick={() => remove(u)}
                  >
                    删除
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function TeamsSection({ teams }: { teams: TeamOut[] }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    const { error } = await api.POST("/api/v1/teams", { body: { name } });
    if (error) {
      toast.error(`创建失败：${apiErrorMessage(error)}`);
      return;
    }
    toast.success("团队已创建");
    setName("");
    queryClient.invalidateQueries({ queryKey: ["teams"] });
  }

  async function handleDelete(team: TeamOut) {
    const { error } = await api.DELETE("/api/v1/teams/{team_id}", {
      params: { path: { team_id: team.id } },
    });
    if (error) {
      toast.error(`删除失败：${apiErrorMessage(error)}`);
      return;
    }
    toast.success(`已删除 ${team.name}`);
    queryClient.invalidateQueries({ queryKey: ["teams"] });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>团队（{teams.length}）</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <form onSubmit={handleCreate} className="flex gap-2">
          <Input
            placeholder="新团队名称"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <Button type="submit" size="sm">
            创建
          </Button>
        </form>
        <ul className="space-y-1">
          {teams.map((t) => (
            <li key={t.id} className="flex items-center rounded-md border px-3 py-1.5 text-sm">
              {t.name}
              <Button
                variant="ghost"
                size="sm"
                className="ml-auto h-6 px-2 text-xs text-muted-foreground"
                onClick={() => handleDelete(t)}
              >
                删除
              </Button>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

export default function AdminPage() {
  const router = useRouter();
  const { data: me, isLoading } = useMe();
  const { data: teams } = useTeams();

  useEffect(() => {
    if (!isLoading && me && me.role !== "admin") {
      router.replace("/dashboard");
    }
  }, [isLoading, me, router]);

  if (!me || me.role !== "admin") {
    return (
      <main className="flex flex-1 items-center justify-center">
        <p className="text-muted-foreground">加载中…</p>
      </main>
    );
  }

  return (
    <main className="flex-1 space-y-4 py-8">
      <h1 className="text-2xl font-semibold">管理</h1>
      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <UsersSection teams={teams ?? []} />
        <TeamsSection teams={teams ?? []} />
      </div>
    </main>
  );
}
