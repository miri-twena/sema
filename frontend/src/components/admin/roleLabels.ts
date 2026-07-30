import type { AdminRole } from "../../lib/api";

// Split out of UserRow.tsx so that component file exports only a component
// (React Fast Refresh requires component-only modules). Shared by UserRow and
// UserDetailDrawer.
export const ROLE_LABEL: Record<AdminRole, string> = {
  client_admin: "Admin",
  analyst: "Analyst",
  viewer: "Viewer",
};
