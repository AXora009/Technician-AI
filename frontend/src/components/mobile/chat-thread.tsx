import { useEffect, useRef } from "react";
import { CheckCircle, ShieldAlert, MessageSquare, Stethoscope } from "lucide-react";
import { Markdown } from "@/components/shared/markdown";
import { SourceList } from "@/components/ask/source-list";
import { FeedbackWidget } from "@/components/ask/feedback-widget";
import { ResolutionCard } from "@/components/ask/resolution-card";
import { Spinner } from "@/components/shared/spinner";
import type { AskMessage, DiagMessage, Tab } from "./types";

interface ChatThreadProps {
  tab: Tab;
  askMsgs: AskMessage[];
  diagMsgs: DiagMessage[];
  loading: boolean;
}

export function ChatThread({ tab, askMsgs, diagMsgs, loading }: ChatThreadProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const count = tab === "ask" ? askMsgs.length : diagMsgs.length;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [count, loading, tab]);

  const empty = count === 0 && !loading;

  return (
    <div className="px-3 py-4 space-y-4">
      {empty && <EmptyState tab={tab} />}

      {tab === "ask"
        ? askMsgs.map((m, i) => <AskBubble key={i} msg={m} />)
        : diagMsgs.map((m, i) => <DiagBubble key={i} msg={m} />)}

      {loading && (
        <div className="flex justify-start">
          <Spinner text={tab === "ask" ? "Searching manuals..." : "Analyzing..."} />
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-primary/10 border border-primary/20 px-3.5 py-2.5">
        <p className="text-sm whitespace-pre-wrap leading-relaxed">{text}</p>
      </div>
    </div>
  );
}

function AssistantShell({
  children,
  accent = "primary",
}: {
  children: React.ReactNode;
  accent?: "primary" | "green" | "destructive";
}) {
  const border =
    accent === "green"
      ? "border-l-green-500"
      : accent === "destructive"
        ? "border-l-destructive"
        : "border-l-primary";
  return (
    <div className="flex justify-start">
      <div className={`max-w-[92%] w-full rounded-xl rounded-bl-sm border border-border border-l-4 ${border} bg-card px-3.5 py-3`}>
        {children}
      </div>
    </div>
  );
}

function AskBubble({ msg }: { msg: AskMessage }) {
  if (msg.role === "user") return <UserBubble text={msg.text} />;
  const { data } = msg;
  return (
    <AssistantShell>
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
          Response &middot; Conv #{data.conversation_id}
        </span>
        <span className="text-[10px] font-mono text-muted-foreground">
          {data.sources.length} source{data.sources.length !== 1 && "s"}
        </span>
      </div>
      <Markdown>{data.answer}</Markdown>
      <SourceList sources={data.sources} />
      {data.conversation_id > 0 && <FeedbackWidget conversationId={data.conversation_id} />}
    </AssistantShell>
  );
}

function DiagBubble({ msg }: { msg: DiagMessage }) {
  if (msg.role === "user") return <UserBubble text={msg.text} />;
  const { data } = msg;
  const safety = data.is_safety_critical;
  const accent = data.is_resolved ? "green" : safety ? "destructive" : "primary";

  return (
    <AssistantShell accent={accent}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
          {safety ? "Safety Hold" : data.is_resolved ? "Resolution" : `Step ${data.step}`}
        </span>
        {data.is_resolved ? (
          <span className="text-[10px] font-mono text-green-400 flex items-center gap-1">
            <CheckCircle className="h-3 w-3" /> Root cause
          </span>
        ) : safety ? (
          <span className="text-[10px] font-mono text-destructive flex items-center gap-1">
            <ShieldAlert className="h-3 w-3" /> Confirm safe
          </span>
        ) : null}
      </div>

      {data.is_resolved && data.resolution ? (
        <ResolutionCard resolution={data.resolution} />
      ) : (
        <Markdown>{data.message}</Markdown>
      )}

      {data.is_resolved && data.sources.length > 0 && <SourceList sources={data.sources} />}
      {data.is_resolved && data.conversation_id != null && (
        <FeedbackWidget conversationId={data.conversation_id} />
      )}
    </AssistantShell>
  );
}

function EmptyState({ tab }: { tab: Tab }) {
  const Icon = tab === "ask" ? MessageSquare : Stethoscope;
  const title = tab === "ask" ? "Ask anything" : "Guided diagnosis";
  const sub =
    tab === "ask"
      ? "Ask about specs, procedures, or prior fixes. Answers are cited from your manuals and field notes."
      : "Describe the problem on the line. I'll walk you through safe, evidence-controlled checks one at a time.";
  return (
    <div className="flex flex-col items-center justify-center text-center px-6 pt-[18vh]">
      <div className="rounded-full border border-border bg-card p-3 mb-4">
        <Icon className="h-6 w-6 text-muted-foreground" />
      </div>
      <p className="text-sm font-medium text-foreground mb-1.5">{title}</p>
      <p className="text-xs text-muted-foreground leading-relaxed max-w-[280px]">{sub}</p>
    </div>
  );
}
