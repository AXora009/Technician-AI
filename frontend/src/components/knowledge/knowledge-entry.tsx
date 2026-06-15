import { Card, CardContent } from "@/components/ui/card";
import { TagBadge } from "@/components/shared/tag-badge";
import type { KnowledgeEntry as KnowledgeEntryType } from "@/types/api";

export function KnowledgeEntry({ entry }: { entry: KnowledgeEntryType }) {
  const meta = entry.metadata;
  const topicPath = meta.topic_path as string[] | undefined;
  const entryType = meta.entry_type as string | undefined;
  const title = meta.title as string | undefined;

  return (
    <Card className="border-border/60">
      <CardContent className="pt-3 pb-3 space-y-1.5">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-medium truncate">
            {title || `Entry #${entry.id}`}
          </span>
          {entryType && <TagBadge type={entryType} />}
        </div>
        {topicPath && (
          <span className="text-[10px] font-mono text-muted-foreground">
            {topicPath.join(" > ")}
          </span>
        )}
        <p className="text-xs text-muted-foreground leading-relaxed line-clamp-3">
          {entry.text}
        </p>
      </CardContent>
    </Card>
  );
}
