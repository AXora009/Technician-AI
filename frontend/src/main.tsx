import { StrictMode, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { ThemeProvider } from "@/context/theme-provider";
import { LangProvider } from "@/i18n";
import { useRegisterSW } from "virtual:pwa-register/react";
import App from "./App";
import "./index.css";

function Root() {
  const { needRefresh: [needRefresh], updateServiceWorker } = useRegisterSW({ immediate: true });
  useEffect(() => {
    if (needRefresh) updateServiceWorker(true);
  }, [needRefresh, updateServiceWorker]);
  return <App />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <LangProvider>
        <Root />
      </LangProvider>
    </ThemeProvider>
  </StrictMode>,
);
