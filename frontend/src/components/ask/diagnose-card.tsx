import { useState } from "react";
import { Send, CheckCircle, ShieldAlert } from "lucide-react";
import { Markdown } from "@/components/shared/markdown";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { SourceList } from "./source-list";
import { FeedbackWidget } from "./feedback-widget";
import { ResolutionCard } from "./resolution-card";
import { Spinner } from "@/components/shared/spinner";
import { api } from "@/hooks/use-api";
import type { DiagnoseResponse, Resolution } from "@/types/api";

interface HistoryEntry {
  role: "user" | "assistant";
  content: string;
}

interface DiagnoseCardProps {
  initial: DiagnoseResponse;
  question?: string;
}

export function DiagnoseCard({ initial, question }: DiagnoseCardProps) {
  const [sessionId] = useState(initial.session_id);
  const [history, setHistory] = useState<HistoryEntry[]>([
    { role: "assistant", content: initial.message },
  ]);
  const [resolved, setResolved] = useState(initial.is_resolved);
  const [resolution, setResolution] = useState<Resolution | null>(initial.resolution ?? null);
  const [resolvedMsgIdx, setResolvedMsgIdx] = useState<number | null>(
    initial.is_resolved ? 0 : null
  );
  const [sources, setSources] = useState(initial.sources);
  const [conversationId, setConversationId] = useState<number | null>(initial.conversation_id);
  const [step, setStep] = useState(initial.step);
  const [isSafetyCritical, setIsSafetyCritical] = useState(initial.is_safety_critical ?? false);
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleStep() {
    const text = answer.trim();
    if (!text || loading) return;

    setHistory((h) => [...h, { role: "user", content: text }]);
    setAnswer("");
    setLoading(true);

    try {
      const res = await api.diagnoseStep(sessionId, text);
      console.log("[DiagnoseCard] step response:", res);
      setHistory((h) => {
        const next = [...h, { role: "assistant" as const, content: res.message }];
        if (res.is_resolved) {
          setResolvedMsgIdx(next.length - 1);
        }
        return next;
      });
      setStep(res.step);
      if (res.is_safety_critical === false) setIsSafetyCritical(false);
      if (res.is_resolved) {
        setResolved(true);
        setResolution(res.resolution ?? null);
        setSources(res.sources);
        setConversationId(res.conversation_id);
      }
    } catch {
      setHistory((h) => [...h, { role: "assistant", content: "Error — please try again." }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className="border-l-4 border-l-green-500">
      {question && (
        <div className="px-4 pt-4 pb-2 border-b border-border">
          <p className="text-[10px] font-mono uppercase tracking-[0.12em] text-muted-foreground mb-1">Problem reported</p>
          <p className="text-sm font-medium text-foreground">{question}</p>
        </div>
      )}
      <CardContent className="pt-4 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-mono text-muted-foreground">
            {isSafetyCritical ? "Safety Hold" : `Diagnostic · Step ${step}`}
          </span>
          {resolved ? (
            <span className="text-xs font-mono text-green-400 flex items-center gap-1">
              <CheckCircle className="h-3 w-3" /> Root cause confirmed
            </span>
          ) : isSafetyCritical ? (
            <span className="text-xs font-mono text-destructive flex items-center gap-1">
              <ShieldAlert className="h-3 w-3" /> Confirm personnel and equipment are safe before diagnosis
            </span>
          ) : step < 3 ? (
            <span className="text-xs font-mono text-muted-foreground">
              {step}/3 &mdash; gathering evidence
            </span>
          ) : (
            <span className="text-xs font-mono text-muted-foreground">
              Narrowing down...
            </span>
          )}
        </div>
        <Separator />

        {/* Conversation history */}
        <div className="space-y-3">
          {history.map((msg, i) => (
            msg.role === "assistant" ? (
              <div key={i} className="text-sm">
                {i === resolvedMsgIdx && resolution ? (
                  <ResolutionCard resolution={resolution} />
                ) : (
                  <Markdown>{msg.content}</Markdown>
                )}
              </div>
            ) : (
              <div key={i} className="text-sm px-3 py-2 rounded-sm bg-primary/10 border border-primary/20">
                <span className="text-[10px] font-mono uppercase text-muted-foreground block mb-1">You</span>
                <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
              </div>
            )
          ))}
        </div>

        {loading && <Spinner text="Analyzing..." />}

        {/* Input for next answer */}
        {!resolved && !loading && (
          <div className="space-y-2 pt-1">
            <Textarea
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              placeholder="Describe what you see..."
              className="min-h-[60px] text-sm bg-card font-mono"
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleStep();
                }
              }}
            />
            <Button
              size="sm"
              disabled={!answer.trim()}
              onClick={handleStep}
              className="font-mono text-[11px] uppercase tracking-wider"
            >
              <Send className="h-3 w-3 mr-1.5" />
              Continue
            </Button>
          </div>
        )}

        {resolved && sources.length > 0 && <SourceList sources={sources} />}
        {resolved && conversationId != null && (
          <FeedbackWidget conversationId={conversationId} />
        )}
      </CardContent>
    </Card>
  );
}
