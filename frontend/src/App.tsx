import { useCallback, useEffect, useState } from "react";
import { Header } from "@/components/layout/header";
import { KnowledgeDrawer } from "@/components/layout/knowledge-drawer";
import { AskForm } from "@/components/ask/ask-form";
import { AnswerCard } from "@/components/ask/answer-card";
import { DiagnoseCard } from "@/components/ask/diagnose-card";
import { EntryList } from "@/components/knowledge/entry-list";
import { Spinner } from "@/components/shared/spinner";
import { api } from "@/hooks/use-api";
import type { AskResponse, DiagnoseResponse, KnowledgeEntry, Topic } from "@/types/api";

type ResultView =
  | { kind: "ask"; data: AskResponse; question: string }
  | { kind: "diagnose"; data: DiagnoseResponse; question: string };

export default function App() {
  const [result, setResult] = useState<ResultView | null>(null);
  const [loading, setLoading] = useState(false);
  const [entries, setEntries] = useState<KnowledgeEntry[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);

  const refresh = useCallback(async () => {
    const [k, t] = await Promise.all([api.knowledge(), api.topics()]);
    setEntries(k.entries);
    setTopics(t.topics);
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  async function handleAsk(question: string) {
    setLoading(true);
    setResult(null);
    try {
      const data = await api.ask(question);
      setResult({ kind: "ask", data, question });
    } catch (err) {
      setResult({
        kind: "ask",
        question,
        data: {
          answer: err instanceof Error ? err.message : "Something went wrong.",
          sources: [],
          conversation_id: 0,
        },
      });
    } finally {
      setLoading(false);
    }
  }

  async function handleDiagnose(question: string) {
    setLoading(true);
    setResult(null);
    try {
      const data = await api.diagnoseStart(question);
      setResult({ kind: "diagnose", data, question });
    } catch (err) {
      setResult({
        kind: "ask",
        question,
        data: {
          answer: err instanceof Error ? err.message : "Diagnose failed.",
          sources: [],
          conversation_id: 0,
        },
      });
    } finally {
      setLoading(false);
    }
  }

  const drawer = <KnowledgeDrawer topics={topics} onUploadComplete={refresh} />;

  return (
    <div className="min-h-screen flex flex-col">
      <Header topicCount={topics.length} entryCount={entries.length} actions={drawer} />

      <div className="flex-1 max-w-[860px] mx-auto w-full px-3 sm:px-6 py-4 sm:py-5 pb-safe">
        <main className="space-y-5">
          <section>
            <h2 className="text-sm font-mono uppercase tracking-[0.15em] text-muted-foreground mb-3">
              &sect; &nbsp;Query &amp; Diagnose
            </h2>
            <AskForm onSubmit={handleAsk} onDiagnose={handleDiagnose} loading={loading} />
          </section>

          {loading && <Spinner />}
          {result?.kind === "ask" && !loading && <AnswerCard result={result.data} question={result.question} />}
          {result?.kind === "diagnose" && !loading && <DiagnoseCard initial={result.data} question={result.question} />}

          {entries.length > 0 && (
            <section>
              <h2 className="text-[10px] font-mono uppercase tracking-[0.15em] text-muted-foreground mb-2 mt-6">
                &sect; &nbsp;Captured Knowledge
              </h2>
              <EntryList entries={entries} />
            </section>
          )}
        </main>
      </div>
    </div>
  );
}
