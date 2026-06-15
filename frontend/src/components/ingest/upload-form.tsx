import { useState, useRef } from "react";
import { Upload, FileText, CheckCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/hooks/use-api";

interface UploadFormProps {
  onComplete: () => void;
}

export function UploadForm({ onComplete }: UploadFormProps) {
  const [status, setStatus] = useState<"idle" | "uploading" | "done" | "error">("idle");
  const [message, setMessage] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFile(file: File) {
    setStatus("uploading");
    setMessage(`Processing ${file.name}...`);
    try {
      const res = await api.ingest(file);
      setMessage(`${res.filename}: ${res.chunks} chunks ingested`);
      setStatus("done");
      onComplete();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Upload failed");
      setStatus("error");
    }
  }

  return (
    <div
      className={`
        border-2 border-dashed rounded-lg p-4 text-center transition-colors
        ${dragOver ? "border-primary bg-primary/5" : "border-border"}
      `}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        const file = e.dataTransfer.files[0];
        if (file) handleFile(file);
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.pptx,.docx,.xlsx,.xls"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
        }}
      />

      {status === "idle" && (
        <>
          <Upload className="h-6 w-6 mx-auto mb-2 text-muted-foreground" />
          <p className="text-xs text-muted-foreground mb-2">
            Drop a PDF, PPTX, DOCX, or Excel here
          </p>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => inputRef.current?.click()}
          >
            <FileText className="h-3.5 w-3.5 mr-1.5" />
            Choose File
          </Button>
        </>
      )}

      {status === "uploading" && (
        <div className="py-2">
          <div className="flex items-center justify-center gap-2 text-xs text-muted-foreground font-mono">
            <div className="h-3.5 w-3.5 border-2 border-primary border-t-transparent rounded-full animate-spin" />
            {message}
          </div>
        </div>
      )}

      {(status === "done" || status === "error") && (
        <div className="py-2 space-y-2">
          <div className={`flex items-center justify-center gap-1.5 text-xs font-mono ${status === "done" ? "text-secondary" : "text-destructive"}`}>
            {status === "done" && <CheckCircle className="h-3.5 w-3.5" />}
            {message}
          </div>
          <Button variant="ghost" size="sm" onClick={() => { setStatus("idle"); setMessage(""); }}>
            Upload another
          </Button>
        </div>
      )}
    </div>
  );
}
