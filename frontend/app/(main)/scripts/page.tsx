"use client";

import { KnowledgePanel } from "@/components/scripts/knowledge-panel";
import { RecommendPanel } from "@/components/scripts/recommend-panel";
import { ScriptLibrary } from "@/components/scripts/script-library";

export default function ScriptsPage() {
  return (
    <main className="flex-1 space-y-4 py-8">
      <h1 className="text-2xl font-semibold">话术</h1>
      <RecommendPanel />
      <div className="grid gap-4 lg:grid-cols-2">
        <ScriptLibrary />
        <KnowledgePanel />
      </div>
    </main>
  );
}
