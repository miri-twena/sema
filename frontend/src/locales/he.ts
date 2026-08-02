// SEMA: the Hebrew mirror of en.ts, read only when an org explicitly opts
// into Hebrew (AGENTS.md's "UI language" bullet). `he` is typed against
// `TranslationKeys` (inferred from en.ts), so a missing/extra/mistyped key
// here is a compile-time error, not a silent runtime gap -- see
// locales.test.ts for the accompanying runtime parity walk.
//
// House style, matching the existing Hebrew copy already in the codebase:
// SEMA is always feminine ("SEMA מזהה", never masculine); gendered verbs/
// imperatives use the plural form ("נסו שוב") to stay gender-neutral rather
// than defaulting to masculine; sentence case, not Title Case; written as
// natural product copy, not literal machine-translated English.

import type { TranslationKeys } from "./en";

export const he: TranslationKeys = {
  common: {
    comingSoon: "בקרוב",
    cancel: "ביטול",
    roles: {
      client_admin: "מנהל/ת",
      analyst: "אנליסט/ית",
      viewer: "צופה",
    },
  },

  chat: {
    placeholder: "אפשר לשאול על הכנסות, לקוחות וקמפיינים...",
    drillPlaceholder: (shortTitle: string) => `אפשר להמשיך לשאול על ${shortTitle}...`,
  },

  sidebar: {
    newConversation: "שיחה חדשה",
    searchConversations: "חיפוש שיחות",
    searchPlaceholder: "חיפוש שיחות...",
    clearSearch: "נקה חיפוש",
    closeSearch: "סגור חיפוש",
    archived: "בארכיון",
    noArchivedChats: "אין שיחות בארכיון.",
    couldNotLoadHistory: "לא ניתן לטעון את היסטוריית השיחות.",
    noConversationsYetPrefix: "עדיין אין שיחות. אפשר להתחיל עם",
    noChatsMatch: (query: string) => `אין שיחות שתואמות ל-"${query}".`,
    showAll: (count: number) => `הצג את כל ${count} →`,
    drillFollowUps: (count: number) => (count === 1 ? "המשך אחד" : `${count} המשכים`),
    groups: {
      pinned: "מוצמדות",
      recent: "אחרונות",
      today: "היום",
      week: "7 הימים האחרונים",
      older: "ישנות יותר",
    },
  },

  menus: {
    conversation: {
      actionsLabel: "פעולות שיחה",
      rename: "שינוי שם",
      pinChat: "הצמדת שיחה",
      unpinChat: "ביטול הצמדה",
      archive: "העברה לארכיון",
      unarchive: "שחזור מארכיון",
      delete: "מחיקה",
      deleteConfirmPrompt: "למחוק את השיחה?",
      rerun: "הרצה מחדש",
    },
  },

  workspace: {
    connected: "מחובר",
    disconnected: "מנותק",
    fallbackLabel: "סביבת עבודה",
    switchWorkspace: "החלפת סביבת עבודה",
    switchWorkspaceLabel: (label: string) => `סביבת עבודה: ${label}. החלפת סביבת עבודה`,
    adminMenuLabel: "תפריט ניהול",
    adminMenuAriaLabel: "ניהול",
    gear: {
      manageOrg: "ניהול הארגון",
      platformConsole: "קונסולת פלטפורמה",
    },
  },

  userMenu: {
    personalSettings: "הגדרות אישיות",
    logOut: "התנתקות",
  },

  messageActions: {
    copyAnswer: "העתקת תשובה",
    copyEntireAnswerTitle: "העתקת התשובה המלאה",
    copyEntireAnswerAriaLabel: "העתקת התשובה המלאה",
    copied: "הועתק",
    copyFailed: "ההעתקה נכשלה",
    retry: "ניסיון חוזר",
    retryTitle: "לשאול את השאלה הזו שוב",
    retryAriaLabel: "ניסיון חוזר על השאלה",
    feedback: {
      up: "תשובה טובה",
      down: "תשובה לא טובה",
      commentPrompt: "מה היה לא בסדר?",
      commentPlaceholder: "לא חובה...",
      send: "שליחה",
      skip: "דלג/י",
    },
  },

  home: {
    greeting: {
      morning: "בוקר טוב",
      afternoon: "צהריים טובים",
      evening: "ערב טוב",
    },
    subtitle: "הנה מה שדורש את תשומת לבך היום.",
    askGuidance: "אפשר לשאול את SEMA כל שאלה על העסק, בשפה חופשית.",
    dailyBrief: "תקציר יומי",
    asOf: (date: string) => `נכון ל-${date}`,
    tellMeMore: "ספרי לי עוד",
    allNormal: "כל המדדים בטווח הרגיל היום",
    businessOverview: "סקירה עסקית",
    topRecommendation: "המלצה מובילה",
    askSemaWhy: "לשאול את SEMA למה",
    startConversation: "התחלת שיחה",
    askAnythingPrompt: "אפשר לשאול כל דבר על העסק שלך — או להתחיל מאחת מהאפשרויות הבאות:",
    trendingInCompany: "פופולרי בארגון שלך",
    briefChip: {
      criticalAlert: (count: number) => (count === 1 ? "התראה קריטית אחת" : `${count} התראות קריטיות`),
      toWatch: (count: number) => `${count} לתשומת לב`,
      allSystemsLive: "כל המערכות פעילות",
      aiAgentOffline: "סוכן ה-AI לא זמין",
      databaseDisconnected: "מסד הנתונים מנותק",
      database: "מסד נתונים",
      aiAgent: "סוכן AI",
      ready: "זמין",
      offline: "לא זמין",
    },
    period: {
      changeLabel: (current: string) => `שינוי תקופה (כרגע ${current})`,
      lastMonth: "החודש האחרון",
      last3Months: "3 החודשים האחרונים",
      last6Months: "6 החודשים האחרונים",
      last12Months: "12 החודשים האחרונים",
      customRange: "טווח מותאם אישית…",
      fromMonth: "מחודש",
      toMonth: "עד חודש",
    },
  },

  newConversation: {
    headline: "מה תרצו לדעת?",
    subtitle: "אפשר לשאול כל דבר על העסק שלך — בשפה חופשית.",
  },

  admin: {
    users: {
      breadcrumb: "ניהול הארגון",
      title: "משתמשים והרשאות",
      subtitle: (members: number, pending: number) =>
        `${members} חברי צוות · ${pending} הזמנות ממתינות`,
      inviteUser: "הזמנת משתמש",
      searchPlaceholder: "חיפוש לפי שם או אימייל",
      allRoles: "כל התפקידים",
      columnUser: "משתמש",
      columnRole: "תפקיד",
      columnDataAccess: "גישה לנתונים",
      columnLastActive: "פעילות אחרונה",
      noUsersMatch: "אין משתמשים התואמים לחיפוש.",
      noUsersYet: "עדיין אין משתמשים.",
      couldNotLoad: "לא ניתן לטעון את המשתמשים. נסו שוב.",
      actionsLabel: (name: string) => `פעולות עבור ${name}`,
      viewDetails: "הצגת פרטים",
      viewDetailsForLabel: (name: string) => `הצגת פרטים עבור ${name}`,
      suspendUser: "השעיית משתמש",
      reactivateUser: "הפעלה מחדש",
      removeFromOrg: "הסרה מהארגון",
      clickAgainToRemove: "לחצו שוב כדי להסיר",
      resend: "שליחה חוזרת",
      youSuffix: "(את/ה)",
      pending: "ממתין",
      inviteExpired: "ההזמנה פגה",
      inviteSentExpiresIn: (days: number) => `הזמנה נשלחה · פגה בעוד ${days} ${days === 1 ? "יום" : "ימים"}`,
      roleForLabel: (name: string) => `תפקיד עבור ${name}`,
      suspendedStatus: "מושעה",
      lastAdminRoleLocked: "לא ניתן לשנות את תפקיד המנהל/ת האחרון/ה הפעיל/ה.",
      lastAdminSuspendLocked: "לא ניתן להשעות את המנהל/ת האחרון/ה הפעיל/ה.",
      lastAdminRemoveLocked: "לא ניתן להסיר את המנהל/ת האחרון/ה הפעיל/ה.",
      lastAdminNotice:
        "בארגון שלכם חייב תמיד להישאר לפחות מנהל/ת פעיל/ה אחד/ת, ולכן לא ניתן להסיר, להשעות או להוריד בדרגה את המנהל/ת האחרון/ה.",
      detail: {
        heading: "פרופיל משתמש",
        close: "סגירה",
        role: "תפקיד",
        dataAccess: "גישה לנתונים",
        status: "סטטוס",
        lastActive: "פעילות אחרונה",
        invitedBy: "הוזמן/ה על ידי",
        joinedOn: "הצטרפות בתאריך",
        active: "פעיל/ה",
        reactivate: "הפעלה מחדש",
        suspend: "השעיה",
        foundingMember: "חבר/ת צוות מייסד/ת",
        unknownDash: "—",
        notJoinedYet: (relativeTime: string) => `עדיין לא הצטרף/ה · הוזמן/ה ${relativeTime}`,
        lastAdminLockedNotice: "זהו/זוהי המנהל/ת האחרון/ה הפעיל/ה בארגון, ולכן לא ניתן לשנות כאן את התפקיד או הסטטוס שלו/שלה.",
      },
      invite: {
        title: "הזמנת משתמש",
        validitySubtitle: "קישור ההזמנה תקף ל-7 ימים.",
        close: "סגירה",
        emailLabel: "כתובת אימייל",
        emailPlaceholder: "name@company.com",
        invalidEmail: "יש להזין כתובת אימייל תקינה.",
        couldNotSend: "לא ניתן היה לשלוח את ההזמנה.",
        roleLabel: "תפקיד",
        dataAccessLabel: "גישה לנתונים",
        scopeNoFinancials: "ללא נתונים פיננסיים",
        scopeSalesOnly: "מכירות בלבד",
        scopeFullAccess: "גישה מלאה",
        adminAlwaysFullAccess: "למנהלים תמיד יש גישה מלאה לנתונים.",
        cancel: "ביטול",
        sending: "שולח…",
        sendInvite: "שליחת הזמנה",
      },
    },
  },
};
