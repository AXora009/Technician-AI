import { FileText, FileSpreadsheet, Download } from "lucide-react";
import { Sheet } from "@/components/ui/sheet";
import { ScrollArea } from "@/components/ui/scroll-area";
import { TopicTree } from "@/components/knowledge/topic-tree";
import type { Topic } from "@/types/api";

interface ManualFile {
  name: string;
  size: number;
  url: string;
}
interface Manual {
  title: string;
  chunks: number;
  source_path: string;
}

interface LibrarySheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  topics: Topic[];
  manualFiles: ManualFile[];
  manuals: Manual[];
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function LibrarySheet({ open, onOpenChange, topics, manualFiles, manuals }: LibrarySheetProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange} side="right" title="Library">
      <ScrollArea className="flex-1 overflow-y-auto">
        <div className="p-4 space-y-6">
          <section>
            <h2 className="text-[10px] font-mono uppercase tracking-[0.15em] text-muted-foreground mb-2">
              Knowledge Tree
            </h2>
            <div className="border border-border rounded-sm p-2">
              <TopicTree topics={topics} />
            </div>
          </section>

          {manualFiles.length > 0 && (
            <section>
              <h2 className="text-[10px] font-mono uppercase tracking-[0.15em] text-muted-foreground mb-2">
                Manuals Library ({manualFiles.length})
              </h2>
              <div className="border border-border rounded-sm divide-y divide-border">
                {manualFiles.map((f) => {
                  const isXlsx = /\.(xlsx|xls)$/i.test(f.name);
                  const isPdf = /\.pdf$/i.test(f.name);
                  const ingested = manuals.find(
                    (m) => m.title === f.name || m.source_path?.endsWith(f.name)
                  );
                  return (
                    <div key={f.name} className="flex items-center gap-2 px-3 py-2">
                      {isXlsx ? (
                        <FileSpreadsheet className="h-3.5 w-3.5 shrink-0 text-emerald-600" />
                      ) : (
                        <FileText className="h-3.5 w-3.5 shrink-0 text-blue-500" />
                      )}
                      <div className="flex-1 min-w-0">
                        <a
                          href={f.url}
                          target={isPdf ? "_blank" : undefined}
                          download={!isPdf ? f.name : undefined}
                          rel="noreferrer"
                          className="text-xs truncate block hover:underline text-foreground"
                          title={f.name}
                        >
                          {f.name}
                        </a>
                        <p className="text-[10px] text-muted-foreground font-mono">
                          {formatBytes(f.size)}
                          {ingested && <span className="ml-1.5 text-emerald-600">· indexed</span>}
                        </p>
                      </div>
                      <a
                        href={f.url}
                        download={f.name}
                        className="shrink-0 rounded p-0.5 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                        title="Download"
                      >
                        <Download className="h-3.5 w-3.5" />
                      </a>
                    </div>
                  );
                })}
              </div>
            </section>
          )}
        </div>
      </ScrollArea>
    </Sheet>
  );
}
