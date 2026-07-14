"use client";

import { AssistantChat } from "@/components/assistant/assistant-chat";

export default function AssistantPage() {
  return (
    <main className="flex-1 space-y-4 py-8">
      <h1 className="text-2xl font-semibold">AI 助手</h1>
      <p className="text-sm text-muted-foreground">
        用一句话查你的线索、商机、客户和话术。助手先查真实数据再回答，只能读不能改；
        对话历史不保存，刷新即清。
      </p>
      <AssistantChat />
    </main>
  );
}
