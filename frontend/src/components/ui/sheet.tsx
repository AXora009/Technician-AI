import { type ReactNode } from "react";
import { Dialog } from "@base-ui/react/dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

interface SheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  side?: "right" | "bottom";
  title: string;
  children: ReactNode;
}

const sidePanel = {
  right:
    "top-0 right-0 h-full w-[340px] max-w-[90vw] border-l data-[starting-style]:translate-x-full data-[ending-style]:translate-x-full",
  bottom:
    "bottom-0 inset-x-0 max-h-[85vh] rounded-t-xl border-t data-[starting-style]:translate-y-full data-[ending-style]:translate-y-full pb-safe",
};

export function Sheet({ open, onOpenChange, side = "right", title, children }: SheetProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm transition-opacity duration-200 data-[starting-style]:opacity-0 data-[ending-style]:opacity-0" />
        <Dialog.Popup
          className={cn(
            "fixed z-50 flex flex-col bg-background shadow-xl border-border transition-transform duration-250 ease-out outline-none",
            sidePanel[side]
          )}
        >
          <div className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
            <Dialog.Title className="text-xs font-mono uppercase tracking-widest text-muted-foreground">
              {title}
            </Dialog.Title>
            <Dialog.Close className="rounded p-1 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors">
              <X className="h-4 w-4" />
            </Dialog.Close>
          </div>
          {children}
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
