# סיכום עבודה על SEMA — להמשך בצ'אט חדש

## הפרויקט
SEMA — יועץ עסקי AI לאיקומרס (תיקיית `product-analytics-ai`). צ'אט בשפה טבעית → SQL מבוסס semantic layer (YAML ב-`sql/semantic/`) → תשובה עם טקסט/KPI/גרף/טבלה/המלצות. פרונט: React 19 + Tailwind (`frontend/`), בקאנד: `sema_core/` + FastAPI (`api/`). מולטי-לקוח (לקוח דמו: E-Commerce). תמיכת RTL מלאה. קונבנציות ב-`AGENTS.md`.

## מה נעשה בשיחה

**סקירת UI/UX מלאה** → 19 המלצות ב-5 קטגוריות, שמורות ב-`SEMA-UX-Review.pdf`. עיקרי הכיוון: קיצור aha-moment (brief אוטומטי, streaming), ניקוי סיידבר, עיצוב שקט יותר (צבע רק עם משמעות), dark mode בהמשך.

**אפיון פאנל ניהול** → `SEMA-Admin-Panel-Spec.pdf`: שתי רמות (קונסולת פלטפורמה + פאנל לקוח), 4 תפקידים — Platform Admin, Client Admin, Analyst, Viewer. החלטה: Analyst ו-Viewer עם גישה מלאה לכל המוצר כולל צ'אט; ההבחנה שמורה לעתיד. חיבורי דאטה נוצרים רק ברמת פלטפורמה (הלקוח רואה סטטוס בלבד).

## קבצי פרומפט לקלוד קוד (בתיקיית הפרויקט)

| קובץ | תוכן | סטטוס |
|---|---|---|
| `sidebar_redesign_prompt.md` | סיידבר = שיחות בלבד בקיבוץ זמן, workspace switcher בתחתית, Trending chips במסך הבית | מומש (לפחות חלקית) |
| `chat_ux_fixes_prompt.md` | גלילה חכמה (תשובה מוצגת מתחילתה), תיקוני RTL ב-DrillChat, שדה `summary` מובנה ("In short" / "סיכום בקצרה") מהסוכן — בלי חילוץ ב-frontend | חלק ממתין |
| `drill_threads_prompt.md` | שיחות drill-down כ-threads מוצמדי-ווידג'ט עם resume ו-badge; מחליף את אישור ה-discard | ממתין |
| `daily_brief_prompt.md` | Daily brief דו-שכבתי: דופק יומי (sparklines, סטטוס מול אותו יום-בשבוע) + כרטיסי תובנה מונעי-אירוע (6 מחוללים, מקס 3, יום שקט = שורה אחת). כותרת נשארת "Daily brief" | ממתין (גרסה חודשית ראשונית מומשה) |
| `progress_panel_prompt.md` | אינדיקטור התקדמות = שורה חיה אחת + לוג בהרחבה; retry כמצב של אותה שורה | ממתין |
| `remove_others_also_asked_prompt.md` | הסרת "Others also asked" מהתשובות (מומש ואז הוחלט להסיר) | ממתין |
| `wide_screen_layout_prompt.md` | רספונסיביות למסך רחב: קונטיינר מדורג, פרוזה צרה + ווידג'טים רחבים, drill לצד השיחה ב-2xl | ממתין |
| `answer_feedback_prompt.md` | Thumbs up/down על תשובות + הערה אופציונלית, אחסון לפי conversation+turn | ממתין |
| `admin_users_screen_prompt.md` | מסך Users and permissions בפאנל לקוח, בלי auth אמיתי (זהות מדומה כ-middleware), seed של 10 משתמשים (מנכ"ל/סמנכ"לים כ-Viewers, אנליסטים, מושעה, הזמנה ממתינה) | מומש — ה-shell קיים |
| `semantic_model_screen_prompt.md` | מסך Semantic model: 5 טאבים (Metrics / Entities / Business rules / Calendar & knowledge / Glossary), זרימת Draft→Validate→Publish, YAML כ-source of truth שרק השרת כותב, גרסאות + restore, אינטגרציה לסוכן | ממתין — הבא בתור |

## החלטות ארכיטקטוניות מרכזיות
- אין auth עדיין — זהות מדומה בשרת, בנויה כ-middleware להחלפה עתידית.
- המודל הסמנטי מורחב מעבר למדדים: ישויות ויחסים, כללים עסקיים (מה נחשב הזמנה), לוח שנה עסקי (Black Friday, תקלות), ידע מוסדי, glossary עברית/אנגלית עם הכרעות למונחים דו-משמעיים. כל פריט מגדיר מה הסוכן עושה איתו (ציטוט כהנחה / סייג / זיהוי סינונים).
- שם הטאב בניווט שונה ל-"Semantic model" (עודכן ידנית ב-`AdminPanel.tsx`).
- Daily brief: הפרדה בין טריות (דופק יומי תמיד) לתובנה (רק כשעוברת סף) — בלי כרטיסים מאולצים.

## צעדים הבאים מוצעים
1. הרצת `semantic_model_screen_prompt.md` (אפשר לפצל: בקאנד+Metrics ואז שאר הטאבים).
2. מסך קסטומיזציית מסך הבית (6.2 באפיון) — עם preview חי.
3. הרצת הפרומפטים הממתינים (סדר מומלץ: drill_threads → chat_ux_fixes → daily_brief).
4. בהמשך: slice של auth אמיתי, מסכי קונסולת הפלטפורמה, dark mode.
