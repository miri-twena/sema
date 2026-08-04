// SEMA: the central English locale file for the UI CHROME (AGENTS.md's
// "UI language" bullet, i18n_language_files_prompt.md). English is every
// org's default; `he.ts` is the Hebrew mirror read when an org opts in
// (useUiLang / document.documentElement.lang). This file is the single
// source of truth for the shape BOTH languages must match -- `TranslationKeys`
// below is inferred from it, so `he.ts` gets a compile-time structural-parity
// check for free (a missing or extra key is a type error, not a runtime gap).
//
// NOT covered here (deliberately, per AGENTS.md): the login page (English-
// always), brand terms (SEMA, "AI Business Advisor"), technical identifiers
// (SQL/YAML/metric ids), and agent-generated answer content (headlines,
// insights, recommendations) -- those follow the QUESTION's language, never
// the org setting, and originate server-side, not from this file.

export const en = {
  common: {
    comingSoon: "Coming soon",
    cancel: "Cancel",
    // Canonical role ids stay internal/English (client_admin, analyst,
    // viewer); these are the user-facing display labels.
    roles: {
      client_admin: "Admin",
      analyst: "Analyst",
      viewer: "Viewer",
    },
  },

  chat: {
    placeholder: "Ask about revenue, customers, campaigns...",
    drillPlaceholder: (shortTitle: string) => `Ask about ${shortTitle}...`,
  },

  // full_data_export_prompt.md: the table widget's CSV export.
  table: {
    downloadCsv: "Download CSV",
    exportAllRows: (count: number) => `Export all ${count.toLocaleString()} rows`,
    exporting: "Exporting…",
    exportRateLimited: "You've reached the export limit. Try again in a bit.",
    exportScopeDenied: "This data is no longer part of your access.",
    exportFailed: "Export failed. Please try again.",
    exportCeilingHit: (ceiling: number) =>
      `This result is larger than the ${ceiling.toLocaleString()}-row export limit. Downloaded the first ${ceiling.toLocaleString()} rows.`,
    // table_cap_notice_prompt.md: always-visible truncation notice (replaces
    // the old subtle "(capped)" hover marker) -- `cap` is the display cap
    // actually applied (derived client-side from the loaded row count, never
    // hardcoded 1000), `total` is the server-computed true total.
    cappedNotice: (cap: number, total: number) =>
      `Showing the first ${cap.toLocaleString()} rows of ${total.toLocaleString()} — the display is capped; Export downloads everything.`,
  },

  sidebar: {
    newConversation: "New conversation",
    searchConversations: "Search conversations",
    searchPlaceholder: "Search conversations...",
    clearSearch: "Clear search",
    closeSearch: "Close search",
    archived: "Archived",
    noArchivedChats: "No archived chats.",
    couldNotLoadHistory: "Couldn't load chat history.",
    noConversationsYetPrefix: "No conversations yet. Start one with",
    noChatsMatch: (query: string) => `No chats match “${query}”.`,
    showAll: (count: number) => `Show all ${count} →`,
    drillFollowUps: (count: number) => `${count} drill-down follow-up${count === 1 ? "" : "s"}`,
    groups: {
      pinned: "Pinned",
      recent: "Recent",
      today: "Today",
      week: "Previous 7 days",
      older: "Older",
    },
  },

  menus: {
    conversation: {
      actionsLabel: "Conversation actions",
      rename: "Rename",
      pinChat: "Pin chat",
      unpinChat: "Unpin chat",
      archive: "Archive",
      unarchive: "Unarchive",
      delete: "Delete",
      deleteConfirmPrompt: "Delete this chat?",
      rerun: "Rerun",
    },
  },

  workspace: {
    connected: "Connected",
    disconnected: "Disconnected",
    fallbackLabel: "Workspace",
    switchWorkspace: "Switch workspace",
    switchWorkspaceLabel: (label: string) => `Workspace: ${label}. Switch workspace`,
    adminMenuLabel: "Admin menu",
    adminMenuAriaLabel: "Admin",
    gear: {
      manageOrg: "Manage organization",
      platformConsole: "Platform console",
    },
  },

  userMenu: {
    personalSettings: "Personal settings",
    logOut: "Log out",
  },

  messageActions: {
    copyAnswer: "Copy answer",
    copyEntireAnswerTitle: "Copy the entire answer",
    copyEntireAnswerAriaLabel: "Copy entire answer",
    copied: "Copied",
    copyFailed: "Copy failed",
    retry: "Retry",
    retryTitle: "Ask this question again",
    retryAriaLabel: "Retry question",
    feedback: {
      up: "Good answer",
      down: "Bad answer",
      commentPrompt: "What was wrong?",
      commentPlaceholder: "Optional...",
      send: "Send",
      skip: "Skip",
    },
  },

  home: {
    greeting: {
      morning: "Good morning",
      afternoon: "Good afternoon",
      evening: "Good evening",
    },
    subtitle: "Here's what needs your attention today.",
    askGuidance: "Ask SEMA anything about your business — in plain language.",
    dailyBrief: "Daily brief",
    asOf: (date: string) => `As of ${date}`,
    tellMeMore: "Tell me more",
    allNormal: "All metrics in their normal range today",
    businessOverview: "Business overview",
    topRecommendation: "Top recommendation",
    askSemaWhy: "Ask SEMA why",
    startConversation: "Start a conversation",
    askAnythingPrompt: "Ask anything about your business — or start from one of these:",
    trendingInCompany: "Trending in your company",
    briefChip: {
      criticalAlert: (count: number) => `${count} critical alert${count > 1 ? "s" : ""}`,
      toWatch: (count: number) => `${count} to watch`,
      allSystemsLive: "All systems live",
      aiAgentOffline: "AI agent offline",
      databaseDisconnected: "Database disconnected",
      database: "Database",
      aiAgent: "AI agent",
      ready: "Ready",
      offline: "Offline",
    },
    period: {
      changeLabel: (current: string) => `Change period (currently ${current})`,
      lastMonth: "Last month",
      last3Months: "Last 3 months",
      last6Months: "Last 6 months",
      last12Months: "Last 12 months",
      customRange: "Custom range…",
      fromMonth: "From month",
      toMonth: "To month",
    },
  },

  // "New conversation"'s clean ask canvas (new_conversation_canvas_prompt.md)
  // -- deliberately separate from `home` above: a distinct screen, not a
  // variant of the dashboard.
  newConversation: {
    headline: "What would you like to know?",
    subtitle: "Ask anything about your business — in plain language.",
  },

  admin: {
    users: {
      breadcrumb: "Organization admin",
      title: "Users and permissions",
      subtitle: (members: number, pending: number) =>
        `${members} member${members === 1 ? "" : "s"} · ${pending} pending invite${pending === 1 ? "" : "s"}`,
      inviteUser: "Invite user",
      searchPlaceholder: "Search by name or email",
      allRoles: "All roles",
      columnUser: "User",
      columnRole: "Role",
      columnDataAccess: "Data access",
      columnLastActive: "Last active",
      noUsersMatch: "No users match your search.",
      noUsersYet: "No users yet.",
      couldNotLoad: "Couldn't load users. Please try again.",
      actionsLabel: (name: string) => `Actions for ${name}`,
      viewDetails: "View details",
      viewDetailsForLabel: (name: string) => `View details for ${name}`,
      suspendUser: "Suspend user",
      reactivateUser: "Reactivate user",
      removeFromOrg: "Remove from org",
      clickAgainToRemove: "Click again to remove",
      resend: "Resend",
      youSuffix: "(you)",
      pending: "Pending",
      inviteExpired: "Invite expired",
      inviteSentExpiresIn: (days: number) => `Invite sent · expires in ${days} day${days === 1 ? "" : "s"}`,
      roleForLabel: (name: string) => `Role for ${name}`,
      suspendedStatus: "Suspended",
      lastAdminRoleLocked: "The last active admin's role can't be changed.",
      lastAdminSuspendLocked: "The last active admin can't be suspended.",
      lastAdminRemoveLocked: "The last active admin can't be removed.",
      lastAdminNotice:
        "Your organization must keep at least one active admin, so that admin can't be removed, suspended, or downgraded.",
      detail: {
        heading: "User profile",
        close: "Close",
        role: "Role",
        dataAccess: "Data access",
        status: "Status",
        lastActive: "Last active",
        invitedBy: "Invited by",
        joinedOn: "Joined on",
        active: "Active",
        reactivate: "Reactivate",
        suspend: "Suspend",
        foundingMember: "Founding member",
        unknownDash: "—",
        notJoinedYet: (relativeTime: string) => `Not joined yet · invited ${relativeTime}`,
        lastAdminLockedNotice: "This is the organization's last active admin, so their role and status can't be changed here.",
      },
      invite: {
        title: "Invite user",
        validitySubtitle: "Invite link is valid for 7 days.",
        close: "Close",
        emailLabel: "Email address",
        emailPlaceholder: "name@company.com",
        invalidEmail: "Enter a valid email address.",
        couldNotSend: "Couldn't send the invite.",
        roleLabel: "Role",
        dataAccessLabel: "Data access",
        scopeNoFinancials: "No financials",
        scopeSalesOnly: "Sales only",
        scopeFullAccess: "Full access",
        adminAlwaysFullAccess: "Admins always have full data access.",
        cancel: "Cancel",
        sending: "Sending…",
        sendInvite: "Send invite",
      },
    },
  },
};

/** The structural contract every locale file must satisfy -- `he.ts` is
 * declared `const he: TranslationKeys = {...}`, so a missing/extra/mistyped
 * key fails the TypeScript build, not just a runtime lookup. */
export type TranslationKeys = typeof en;
