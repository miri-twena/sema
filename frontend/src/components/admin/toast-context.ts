import { createContext, useContext } from "react";

// Split from Toast.tsx so that file exports only a component (React Fast Refresh
// requires component-only modules). The provider lives in Toast.tsx; the
// context and hook live here.
export const ToastContext = createContext<(message: string) => void>(() => {});

/** Raise a failure toast: `toast("Couldn't update role")`. Success is silent. */
export function useToast(): (message: string) => void {
  return useContext(ToastContext);
}
