import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Markdown } from "@/components/shared/markdown";
import { SourceList } from "./source-list";
import { FeedbackWidget } from "./feedback-widget";
import type { AskResponse } from "@/types/api";

export function AnswerCard({ result, question }: { result: AskResponse; question?: string }) {
  return (
    <Card className="border-l-4 border-l-primary">
      <CardContent className="pt-4 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-mono text-muted-foreground">
            Response &middot; Conv #{result.conversation_id}
          </span>
          <span className="text-xs font-mono text-muted-foreground">
            {result.sources.length} source{result.sources.length !== 1 && "s"} cited
          </span>
        </div>
        {question && (
          <p className="text-sm font-medium text-foreground border-l-2 border-muted-foreground/30 pl-3 italic">
            {question}
          </p>
        )}
        <Separator />
        <Markdown>{result.answer}</Markdown>
        <SourceList sources={result.sources} />
        <FeedbackWidget conversationId={result.conversation_id} />
      </CardContent>
    </Card>
  );
}
