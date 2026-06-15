import { useCallback, useEffect, useRef, useState } from "react";
import { X, BookOpen, FileText, FileSpreadsheet, Download } from "lucide-react";
import { TopicTree } from "@/components/knowledge/topic-tree";
import { UploadForm } from "@/components/ingest/upload-form";
import { ScrollArea } from "@/components/ui/scroll-area";
import { api } from "@/hooks/use-api";
import type { Topic } from "@/types/api";

interface Manual { title: string; chunks: number; source_path: string; }
interface ManualFile { name: string; size: number; url: string; }

interface KnowledgeDrawerProps {
  topics: Topic[];
  onUploadComplete: () => void;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function KnowledgeDrawer({ topics, onUploadComplete }: KnowledgeDrawerProps) {
  const [open, setOpen] = useState(false);
  const [manuals, setManuals] = useState<Manual[]>([]);
  const [manualFiles, setManualFiles] = useState<ManualFile[]>([]);
  const drawerRef = useRef<HTMLDivElement>(null);

  const refreshManuals = useCallback(async () => {
    const [mRes, fRes] = await Promise.all([api.manuals(), api.manualFiles()]);
    setManuals(mRes.manuals);
    setManualFiles(fRes.files);
  }, []);

  useEffect(() => { refreshManuals(); }, [refreshManuals]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  return (
    <>
      {/* Trigger button */}
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-sm border border-border bg-card hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
        title="Manuals & Knowledge Tree"
      >
        <BookOpen className="h-4 w-4" />
        <span className="text-[11px] font-mono uppercase tracking-wider hidden sm:inline">Library</span>
      </button>

      {/* Backdrop */}
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm"
          onClick={() => setOpen(false)}
        />
      )}

      {/* Drawer panel */}
      <div
        ref={drawerRef}
        className={`fixed top-0 right-0 z-50 h-full w-[340px] max-w-[90vw] bg-background border-l border-border shadow-xl flex flex-col transition-transform duration-200 ease-in-out ${open ? "translate-x-0" : "translate-x-full"}`}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
          <span className="text-xs font-mono uppercase tracking-widest text-muted-foreground">Library</span>
          <button
            onClick={() => setOpen(false)}
            className="rounded p-1 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <ScrollArea className="flex-1 overflow-y-auto">
          <div className="p-4 space-y-6">

            {/* Knowledge Tree */}
            <section>
              <h2 className="text-[10px] font-mono uppercase tracking-[0.15em] text-muted-foreground mb-2">
                Knowledge Tree
              </h2>
              <div className="border border-border rounded-sm">
                <div className="p-2">
                  <TopicTree topics={topics} />
                </div>
              </div>
            </section>

            {/* Manuals Library */}
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
                        {isXlsx
                          ? <FileSpreadsheet className="h-3.5 w-3.5 shrink-0 text-emerald-600" />
                          : <FileText className="h-3.5 w-3.5 shrink-0 text-blue-500" />
                        }
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

            {/* Upload */}
            <section>
              <h2 className="text-[10px] font-mono uppercase tracking-[0.15em] text-muted-foreground mb-2">
                Add a Manual
              </h2>
              <UploadForm onComplete={() => { onUploadComplete(); refreshManuals(); }} />
            </section>

          </div>
        </ScrollArea>
      </div>
    </>
  );
}
