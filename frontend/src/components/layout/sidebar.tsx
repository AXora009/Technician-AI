import { useCallback, useEffect, useState } from "react";
import { X, FileText, Download, FileSpreadsheet } from "lucide-react";
import { TopicTree } from "@/components/knowledge/topic-tree";
import { UploadForm } from "@/components/ingest/upload-form";
import { ScrollArea } from "@/components/ui/scroll-area";
import { api } from "@/hooks/use-api";
import type { Topic } from "@/types/api";

interface Manual { title: string; chunks: number; source_path: string; }
interface ManualFile { name: string; size: number; url: string; }

interface SidebarProps {
  topics: Topic[];
  onUploadComplete: () => void;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function Sidebar({ topics, onUploadComplete }: SidebarProps) {
  const [manuals, setManuals] = useState<Manual[]>([]);
  const [manualFiles, setManualFiles] = useState<ManualFile[]>([]);
  const [deleting, setDeleting] = useState<string | null>(null);

  const refreshManuals = useCallback(async () => {
    const [mRes, fRes] = await Promise.all([api.manuals(), api.manualFiles()]);
    setManuals(mRes.manuals);
    setManualFiles(fRes.files);
  }, []);

  useEffect(() => { refreshManuals(); }, [refreshManuals]);

  async function handleDelete(title: string) {
    if (!confirm(`Delete "${title}" and all its chunks?`)) return;
    setDeleting(title);
    try {
      await api.deleteManual(title);
      await Promise.all([refreshManuals(), onUploadComplete()]);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setDeleting(null);
    }
  }

  return (
    <aside className="w-full lg:w-[320px] shrink-0 space-y-5">
      <section>
        <h2 className="text-[10px] font-mono uppercase tracking-[0.15em] text-muted-foreground mb-2">
          Knowledge Tree
        </h2>
        <div className="border border-border rounded-sm">
          <ScrollArea className="h-[360px] p-2">
            <TopicTree topics={topics} />
          </ScrollArea>
        </div>
      </section>

      {manualFiles.length > 0 && (
        <section>
          <h2 className="text-[10px] font-mono uppercase tracking-[0.15em] text-muted-foreground mb-2">
            Manuals Library ({manualFiles.length})
          </h2>
          <div className="border border-border rounded-sm divide-y divide-border">
            {manualFiles.map((f) => {
              const isXlsx = f.name.match(/\.(xlsx|xls)$/i);
              const isPdf = f.name.match(/\.pdf$/i);
              const ingested = manuals.find(m => m.title === f.name || m.source_path?.endsWith(f.name));
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

      {manuals.length > 0 && (
        <section>
          <h2 className="text-[10px] font-mono uppercase tracking-[0.15em] text-muted-foreground mb-2">
            Uploaded Manuals
          </h2>
          <div className="border border-border rounded-sm divide-y divide-border">
            {manuals.map((m) => (
              <div key={m.title} className="flex items-center gap-2 px-3 py-2">
                <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                <div className="flex-1 min-w-0">
                  <p className="text-xs truncate">{m.title}</p>
                  <p className="text-[10px] text-muted-foreground font-mono">{m.chunks} chunks</p>
                </div>
                <button
                  onClick={() => handleDelete(m.title)}
                  disabled={deleting === m.title}
                  className="shrink-0 rounded p-0.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors disabled:opacity-40"
                  title="Delete manual"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      <section>
        <h2 className="text-[10px] font-mono uppercase tracking-[0.15em] text-muted-foreground mb-2">
          Add a Manual
        </h2>
        <UploadForm onComplete={() => { onUploadComplete(); refreshManuals(); }} />
      </section>
    </aside>
  );
}
