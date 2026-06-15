import { useCallback, useEffect, useState } from "react";
import { MessageSquare, Stethoscope } from "lucide-react";
import { api } from "@/hooks/use-api";
import { cn } from "@/lib/utils";
import type { DiagnoseResponse, Topic } from "@/types/api";
import { MobileTopBar } from "./mobile-top-bar";
import { ChatThread } from "./chat-thread";
import { ChatComposer } from "./chat-composer";
import { LibrarySheet } from "./library-sheet";
import { UploadSheet } from "./upload-sheet";
import type { AskMessage, DiagMessage, Tab } from "./types";

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

export function MobileApp() {
  const [tab, setTab] = useState<Tab>("ask");
  const [loading, setLoading] = useState(false);

  const [askMsgs, setAskMsgs] = useState<AskMessage[]>([]);
  const [diagMsgs, setDiagMsgs] = useState<DiagMessage[]>([]);
  const [session, setSession] = useState<DiagnoseResponse | null>(null);

  const [libraryOpen, setLibraryOpen] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);

  const [topics, setTopics] = useState<Topic[]>([]);
  const [manualFiles, setManualFiles] = useState<ManualFile[]>([]);
  const [manuals, setManuals] = useState<Manual[]>([]);

  const refresh = useCallback(async () => {
    const [t, m, f] = await Promise.all([api.topics(), api.manuals(), api.manualFiles()]);
    setTopics(t.topics);
    setManuals(m.manuals);
    setManualFiles(f.files);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function handleAsk(text: string) {
    setAskMsgs((m) => [...m, { role: "user", text }]);
    setLoading(true);
    try {
      const data = await api.ask(text);
      setAskMsgs((m) => [...m, { role: "assistant", data }]);
    } catch (err) {
      setAskMsgs((m) => [
        ...m,
        {
          role: "assistant",
          data: {
            answer: err instanceof Error ? err.message : "Something went wrong.",
            sources: [],
            conversation_id: 0,
          },
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  async function handleDiagnose(text: string) {
    setDiagMsgs((m) => [...m, { role: "user", text }]);
    setLoading(true);
    const fresh = !session || session.is_resolved;
    try {
      const data = fresh
        ? await api.diagnoseStart(text)
        : await api.diagnoseStep(session!.session_id, text);
      setSession(data);
      setDiagMsgs((m) => [...m, { role: "assistant", data }]);
    } catch {
      // Surface as a resolved-less assistant note without breaking the session.
      setDiagMsgs((m) => [
        ...m,
        {
          role: "assistant",
          data: {
            message: "Error — please try again.",
            is_resolved: false,
            sources: [],
            conversation_id: null,
            session_id: session?.session_id ?? "",
            step: session?.step ?? 0,
          },
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col h-[100dvh] overflow-hidden">
      <header className="shrink-0">
        <MobileTopBar
          onOpenLibrary={() => setLibraryOpen(true)}
          onOpenUpload={() => setUploadOpen(true)}
        />
        <TabSwitcher tab={tab} onChange={setTab} />
      </header>

      <main className="flex-1 overflow-y-auto overscroll-contain">
        <ChatThread tab={tab} askMsgs={askMsgs} diagMsgs={diagMsgs} loading={loading} />
      </main>

      <footer className="shrink-0 border-t border-border bg-background pb-safe">
        <ChatComposer
          tab={tab}
          loading={loading}
          onSubmit={tab === "ask" ? handleAsk : handleDiagnose}
        />
      </footer>

      <LibrarySheet
        open={libraryOpen}
        onOpenChange={setLibraryOpen}
        topics={topics}
        manualFiles={manualFiles}
        manuals={manuals}
      />
      <UploadSheet
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        onComplete={refresh}
      />
    </div>
  );
}

function TabSwitcher({ tab, onChange }: { tab: Tab; onChange: (t: Tab) => void }) {
  const tabs: { id: Tab; label: string; Icon: typeof MessageSquare }[] = [
    { id: "ask", label: "Ask", Icon: MessageSquare },
    { id: "diagnose", label: "Diagnose", Icon: Stethoscope },
  ];
  return (
    <div className="flex items-center gap-1 p-1.5 border-b border-border">
      {tabs.map(({ id, label, Icon }) => (
        <button
          key={id}
          onClick={() => onChange(id)}
          className={cn(
            "flex-1 flex items-center justify-center gap-1.5 h-9 rounded-md text-xs font-mono uppercase tracking-wider transition-colors",
            tab === id
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground hover:bg-muted"
          )}
        >
          <Icon className="h-3.5 w-3.5" />
          {label}
        </button>
      ))}
    </div>
  );
}
