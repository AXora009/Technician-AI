import { Moon, Sun, Monitor } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useThemeContext } from "@/context/theme-provider";

const CYCLE: Array<"light" | "dark" | "system"> = ["light", "dark", "system"];

export function ThemeToggle() {
  const { theme, setTheme } = useThemeContext();
  const next = CYCLE[(CYCLE.indexOf(theme) + 1) % CYCLE.length];
  const Icon = theme === "dark" ? Moon : theme === "light" ? Sun : Monitor;

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={() => setTheme(next)}
      title={`Theme: ${theme}`}
      className="h-8 w-8"
    >
      <Icon className="h-4 w-4" />
    </Button>
  );
}
