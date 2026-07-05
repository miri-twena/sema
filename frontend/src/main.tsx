import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.tsx";
import { ErrorBoundary } from "./components/ErrorBoundary";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary
      fallback={
        <div className="flex h-screen items-center justify-center text-sm text-muted">
          Something went wrong. Please refresh the page.
        </div>
      }
    >
      <App />
    </ErrorBoundary>
  </StrictMode>,
);
