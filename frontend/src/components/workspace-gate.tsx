import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useLang } from "@/i18n";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

async function login(code: string): Promise<boolean> {
  const res = await fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  });
  return res.ok;
}

export function WorkspaceGate({ children }: { children: ReactNode }) {
  const { t } = useLang();
  const [state, setState] = useState<"loading" | "in" | "out">("loading");
  const [code, setCode] = useState("");
  const [invalid, setInvalid] = useState(false);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    // A shared link like /?code=XXXX logs in directly.
    const url = new URL(window.location.href);
    const fromLink = url.searchParams.get("code");
    if (fromLink) {
      url.searchParams.delete("code");
      window.history.replaceState(null, "", url.toString());
      login(fromLink).then((ok) => {
        setInvalid(!ok);
        setState(ok ? "in" : "out");
      });
      return;
    }
    fetch("/api/me")
      .then((res) => setState(res.ok ? "in" : "out"))
      .catch(() => setState("out"));
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const ok = await login(code.trim());
    setInvalid(!ok);
    if (ok) setState("in");
  }

  if (state === "in") return <>{children}</>;
  if (state === "loading") return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background">
      <form
        onSubmit={handleSubmit}
        className="w-72 rounded-lg border border-border bg-card p-6 shadow-lg text-center space-y-4"
      >
        <div>
          <h2 className="text-base font-semibold">{t.ws_title}</h2>
          <p className="text-xs text-muted-foreground mt-1">{t.ws_subtitle}</p>
        </div>
        <Input
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder={t.ws_placeholder}
          autoFocus
        />
        {invalid && <p className="text-xs text-destructive">{t.ws_invalid}</p>}
        <Button type="submit" className="w-full" disabled={!code.trim()}>
          {t.ws_submit}
        </Button>
      </form>
    </div>
  );
}
