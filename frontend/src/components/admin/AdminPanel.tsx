import { useState, type ComponentType } from "react";
import {
  ArrowLeft,
  BookOpen,
  Building2,
  Database,
  LayoutDashboard,
  ScrollText,
  Users,
} from "lucide-react";
import { ToastProvider } from "./Toast";
import { UsersScreen } from "./UsersScreen";
import { SemanticModelScreen } from "./semantic/SemanticModelScreen";
import { OrgSettingsScreen } from "./OrgSettingsScreen";
import { AuditLogScreen } from "./AuditLogScreen";
import { HomeConfigScreen } from "./HomeConfigScreen";
import { DataSourcesScreen } from "./DataSourcesScreen";
import { Logo } from "../brand/Logo";

// The client panel's nav (spec §4). Every item is built now; none render as
// disabled "Coming soon" placeholders any more.
type NavId = "users" | "semantic-model" | "org" | "audit" | "home" | "sources";
const NAV: Array<{ id: NavId | string; label: string; icon: ComponentType<{ size?: number }>; active: boolean }> = [
  { id: "users", label: "Users and permissions", icon: Users, active: true },
  { id: "home", label: "Home screen", icon: LayoutDashboard, active: true },
  { id: "sources", label: "Data sources", icon: Database, active: true },
  { id: "semantic-model", label: "Semantic model", icon: BookOpen, active: true },
  { id: "org", label: "Organization settings", icon: Building2, active: true },
  { id: "audit", label: "Audit log", icon: ScrollText, active: true },
];

/**
 * The client admin panel (spec §6): a full-page surface with its own secondary
 * navigation, opened from the sidebar's gear. Same design tokens as the main
 * app. Users and Semantic model are active in this slice; the other nav items
 * are present but disabled. "Back to SEMA" returns to the chat app.
 */
export function AdminPanel({
  clientLabel,
  onClose,
}: {
  clientLabel: string;
  onClose: () => void;
}) {
  const [active, setActive] = useState<NavId>("users");

  return (
    <ToastProvider>
      <div className="flex h-screen bg-bg text-ink">
        {/* Secondary nav */}
        <aside className="w-64 shrink-0 h-full border-e border-line bg-surface flex flex-col">
          <div className="p-4 border-b border-line">
            <button
              onClick={onClose}
              className="inline-flex items-center gap-1.5 text-[0.82rem] text-muted hover:text-ink transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 rounded"
            >
              <ArrowLeft size={15} /> Back to SEMA
            </button>
            <div className="mt-3">
              <Logo size={22} />
            </div>
            <div className="mt-1.5 text-[0.7rem] font-semibold uppercase tracking-wide text-faint">
              Organization admin
            </div>
          </div>

          <nav className="flex-1 overflow-auto p-2">
            {NAV.map(({ id, label, icon: Icon, active: isActive }) =>
              isActive ? (
                <button
                  key={id}
                  onClick={() => setActive(id as NavId)}
                  aria-current={active === id ? "page" : undefined}
                  className={`w-full text-start flex items-center gap-2.5 rounded-lg px-3 py-2 text-[0.85rem] transition ${
                    active === id
                      ? "bg-primary/10 text-primary-dark font-medium"
                      : "text-ink hover:bg-surfaceAlt"
                  }`}
                >
                  <Icon size={16} />
                  <span className="flex-1">{label}</span>
                  {active === id && (
                    <span
                      className="shrink-0 w-[3px] h-[15px] rounded-full bg-primary"
                      aria-hidden
                    />
                  )}
                </button>
              ) : (
                <div
                  key={id}
                  aria-disabled="true"
                  title="Coming soon"
                  className="w-full flex items-center gap-2.5 rounded-lg px-3 py-2 text-[0.85rem] text-faint cursor-default select-none"
                >
                  <Icon size={16} />
                  <span className="flex-1">{label}</span>
                  <span className="shrink-0 rounded-full bg-surfaceAlt px-1.5 py-0.5 text-[0.6rem] font-medium text-muted">
                    Soon
                  </span>
                </div>
              ),
            )}
          </nav>
        </aside>

        {/* Content */}
        <main className="flex-1 min-w-0 overflow-auto sema-scroll">
          {active === "users" && <UsersScreen clientLabel={clientLabel} />}
          {active === "semantic-model" && <SemanticModelScreen clientLabel={clientLabel} />}
          {active === "org" && <OrgSettingsScreen clientLabel={clientLabel} />}
          {active === "audit" && <AuditLogScreen clientLabel={clientLabel} />}
          {active === "home" && <HomeConfigScreen clientLabel={clientLabel} />}
          {active === "sources" && <DataSourcesScreen clientLabel={clientLabel} />}
        </main>
      </div>
    </ToastProvider>
  );
}
