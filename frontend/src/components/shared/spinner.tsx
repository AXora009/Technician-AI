export function Spinner({ text = "Thinking..." }: { text?: string }) {
  return (
    <div className="flex items-center gap-2 py-4 text-muted-foreground">
      <div className="flex gap-1">
        <span className="h-1.5 w-1.5 rounded-full bg-primary animate-bounce [animation-delay:0ms]" />
        <span className="h-1.5 w-1.5 rounded-full bg-primary animate-bounce [animation-delay:150ms]" />
        <span className="h-1.5 w-1.5 rounded-full bg-primary animate-bounce [animation-delay:300ms]" />
      </div>
      <span className="text-sm font-mono">{text}</span>
    </div>
  );
}
