import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const TYPE_STYLES: Record<string, string> = {
  specification: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300",
  procedure: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300",
  warning: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300",
  troubleshooting: "bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300",
  reference: "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300",
};

export function TagBadge({ type }: { type: string }) {
  return (
    <Badge
      variant="secondary"
      className={cn(
        "text-[10px] font-mono uppercase tracking-wider px-1.5 py-0",
        TYPE_STYLES[type]
      )}
    >
      {type}
    </Badge>
  );
}
