import { type ReactNode } from "react";
import { ThemeToggle } from "@/components/shared/theme-toggle";

interface HeaderProps {
  topicCount: number;
  entryCount: number;
  actions?: ReactNode;
}

export function Header({ topicCount, entryCount, actions }: HeaderProps) {
  return (
    <header>
      <div className="max-w-[1320px] mx-auto px-3 sm:px-6">
        {/* Letterhead row */}
        <div className="flex items-center justify-between py-2.5 sm:py-3 border-b border-border">
          <h1 className="font-mono text-[22px] sm:text-[28px] tracking-[0.08em] sm:tracking-[0.12em] leading-none uppercase">
            Technician <span className="text-green-400">AI</span><span className="text-green-400 animate-pulse">_</span>
          </h1>
          <div className="flex items-center gap-3">
            <dl className="hidden sm:flex items-center gap-6 text-[10px] font-mono uppercase tracking-[0.15em] text-muted-foreground">
              <div className="flex items-center gap-1.5">
                <dt>FK-CONSOLE</dt>
              </div>
              <div className="flex items-center gap-1.5">
                <dt className="text-muted-foreground/60">0.1 ALPHA</dt>
              </div>
              <div className="flex items-center gap-1.5">
                <dt>&#9679; ONLINE</dt>
              </div>
            </dl>
            {actions}
            <ThemeToggle />
          </div>
        </div>

        {/* Stats subtitle bar */}
        <div className="flex items-center gap-4 py-2 text-[10px] font-mono uppercase tracking-[0.15em] text-muted-foreground border-b-2 border-foreground/20">
          <span>FIELD KNOWLEDGE: <span className="text-primary">{topicCount} TOPICS</span></span>
          <span className="text-border">|</span>
          <span>ONGOING: <span className="text-primary">{entryCount} FIELD NOTES</span></span>
        </div>
      </div>
    </header>
  );
}
