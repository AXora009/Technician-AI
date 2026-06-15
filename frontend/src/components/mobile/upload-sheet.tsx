import { Sheet } from "@/components/ui/sheet";
import { UploadForm } from "@/components/ingest/upload-form";

interface UploadSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onComplete: () => void;
}

export function UploadSheet({ open, onOpenChange, onComplete }: UploadSheetProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange} side="bottom" title="Add a Manual">
      <div className="p-4">
        <p className="text-xs text-muted-foreground mb-3 leading-relaxed">
          PDF, PPTX, DOCX, or Excel. The file is chunked, embedded, and added to the searchable
          knowledge base.
        </p>
        <UploadForm onComplete={onComplete} />
      </div>
    </Sheet>
  );
}
