import { createContext, useContext, type ReactNode } from "react";
import { useTheme } from "@/hooks/use-theme";

type ThemeCtx = ReturnType<typeof useTheme>;

const Ctx = createContext<ThemeCtx | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const value = useTheme();
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useThemeContext(): ThemeCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useThemeContext must be used within ThemeProvider");
  return ctx;
}
