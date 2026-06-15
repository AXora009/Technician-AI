import { useState } from "react";
import { ChevronDown, ChevronRight, BookOpen, Lightbulb } from "lucide-react";
import { TagBadge } from "@/components/shared/tag-badge";
import type { Source } from "@/types/api";

export function SourceList({ sources }: { sources: Source[] }) {
  const [open, setOpen] = useState(false);
  if (!sources.length) return null;

  return (
    <div className="border-t border-border pt-3 mt-3">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-xs font-mono text-muted-foreground hover:text-foreground transition-colors"
      >
        {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        {sources.length} source{sources.length !== 1 && "s"} cited
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          {sources.map((s) => (
            <SourceItem key={s.id} source={s} />
          ))}
        </div>
      )}
    </div>
  );
}

function SourceItem({ source }: { source: Source }) {
  const meta = source.metadata;
  const isManual = source.kind === "manual_chunk";
  const Icon = isManual ? BookOpen : Lightbulb;

  let label = isManual
    ? `${(meta.manual_title as string) || "Manual"}`
    : "Field note";

  if (isManual && meta.page) label += `, p.${meta.page}`;
  if (isManual && meta.slide) label += `, slide ${meta.slide}`;

  const topicPath = meta.topic_path as string[] | undefined;
  const entryType = meta.entry_type as string | undefined;

  return (
    <div className="pl-4 border-l-2 border-muted text-xs space-y-1">
      <div className="flex items-center gap-2">
        <Icon className="h-3 w-3 text-muted-foreground shrink-0" />
        <span className="font-medium text-foreground/80">[#{source.index}] {label}</span>
        {entryType && <TagBadge type={entryType} />}
      </div>
      {topicPath && (
        <span className="text-muted-foreground font-mono">
          {topicPath.join(" > ")}
        </span>
      )}
      <p className="text-muted-foreground leading-relaxed line-clamp-2">
        {source.preview}
      </p>
    </div>
  );
}
