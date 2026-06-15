import { KnowledgeEntry } from "./knowledge-entry";
import type { KnowledgeEntry as KnowledgeEntryType } from "@/types/api";

export function EntryList({ entries }: { entries: KnowledgeEntryType[] }) {
  if (!entries.length) {
    return (
      <p className="text-xs text-muted-foreground font-mono py-4 text-center">
        No field notes captured yet.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {entries.map((e) => (
        <KnowledgeEntry key={e.id} entry={e} />
      ))}
    </div>
  );
}
