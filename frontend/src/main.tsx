import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { enforceClientSessionVersion } from "./sessionVersion";

enforceClientSessionVersion();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary label="root">
      <App />
    </ErrorBoundary>
  </StrictMode>
);
