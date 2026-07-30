import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.tsx";
import { LoginPage } from "./components/login/LoginPage.tsx";
import { ErrorBoundary } from "./components/ErrorBoundary";

// /login is a full-page route OUTSIDE the chat app shell (auth_login_prompt.md
// Part 0), same "no router dependency" approach the admin panel uses (a plain
// state check, not a new deps like react-router) -- read once at boot since
// this never changes without a full navigation. The app itself is untouched
// and stays reachable at every other path with today's mock identity.
const isLoginRoute = window.location.pathname === "/login";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary
      fallback={
        <div className="flex h-screen items-center justify-center text-sm text-muted">
          Something went wrong. Please refresh the page.
        </div>
      }
    >
      {isLoginRoute ? <LoginPage /> : <App />}
    </ErrorBoundary>
  </StrictMode>,
);
