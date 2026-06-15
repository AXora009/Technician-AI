import { ListTree, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/shared/theme-toggle";

interface MobileTopBarProps {
  onOpenLibrary: () => void;
  onOpenUpload: () => void;
}

export function MobileTopBar({ onOpenLibrary, onOpenUpload }: MobileTopBarProps) {
  return (
    <div className="flex items-center justify-between px-3 h-12 border-b border-border">
      <h1 className="font-mono text-[17px] tracking-[0.06em] leading-none uppercase">
        Technician <span className="text-green-400">AI</span>
        <span className="text-green-400 animate-pulse">_</span>
      </h1>
      <div className="flex items-center gap-0.5">
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={onOpenLibrary}
          title="Knowledge tree & manuals"
          aria-label="Open knowledge library"
        >
          <ListTree className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={onOpenUpload}
          title="Upload a manual"
          aria-label="Upload a manual"
        >
          <Upload className="h-4 w-4" />
        </Button>
        <ThemeToggle />
      </div>
    </div>
  );
}
