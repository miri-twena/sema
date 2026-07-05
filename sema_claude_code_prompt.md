# SEMA — פרומפט לקלוד קוד: שלושה שיפורים מרכזיים

## הוראות פתיחה

לפני שאתה כותב שורת קוד אחת, קרא את כל הקבצים הבאים:

```
app/main.py
app/wiring.py
app/db.py
app/agent/agent.py
app/agent/prompts.py
app/agent/semantic.py
app/agent/tools.py
app/components/chat.py
app/components/sidebar.py
app/components/styles.py
app/components/kpi_cards.py
docker-compose.yml
.env.example
sql/semantic/revenue.yaml
sql/semantic/churn_risk.yaml
sql/semantic/aov.yaml
sql/semantic/active_customers.yaml
sql/insurance/schema.sql
```

הפרויקט הוא **SEMA** — AI Business Advisor מבוסס Streamlit + Claude API + PostgreSQL.
אנחנו מוסיפים שלושה features בפעם אחת. בצע אותם **בסדר הזה בדיוק** — כל שלב מניח
שהשלב הקודם הושלם ובודק.

---

## PHASE 1 — Multi-Client Support (הפרדת לקוחות)

### הקשר

כרגע קיימת תמיכה חלקית ב-multi-client דרך `SEMA_CLIENT` env var בלבד.
יש שני לקוחות: ecommerce (`sema_db`) ו-insurance (`insurance_db`).
ה-connection נשמר ב-`@st.cache_resource` ולא מתאפס כשמחליפים לקוח.
ה-`SEMANTIC_DIR` מחושב ב-import time, לא דינמי.
ה-docker-compose מגדיר רק DB אחד.

### 1.1 — docker-compose.yml + .env.example

עדכן את `docker-compose.yml` כך שיפעילו **שני services** של PostgreSQL:

```yaml
services:
  postgres_ecommerce:
    image: postgres:16
    container_name: sema-postgres-ecommerce
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-sema_db}
      POSTGRES_USER: ${POSTGRES_USER:-sema_user}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-sema_password}
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    volumes:
      - sema_pgdata_ecommerce:/var/lib/postgresql/data

  postgres_insurance:
    image: postgres:16
    container_name: sema-postgres-insurance
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB_INSURANCE:-insurance_db}
      POSTGRES_USER: ${POSTGRES_USER:-sema_user}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-sema_password}
    ports:
      - "${POSTGRES_PORT_INSURANCE:-5433}:5432"
    volumes:
      - sema_pgdata_insurance:/var/lib/postgresql/data

volumes:
  sema_pgdata_ecommerce:
  sema_pgdata_insurance:
```

עדכן `.env.example` — הוסף:
```
POSTGRES_DB_INSURANCE=insurance_db
POSTGRES_PORT_INSURANCE=5433
POSTGRES_HOST_INSURANCE=localhost
```

### 1.2 — config/clients.yaml (קובץ חדש)

צור תיקייה `config/` בשורש הפרויקט וצור בתוכה `clients.yaml`:

```yaml
clients:
  - id: ecommerce
    label: "🛍️ E-Commerce"
    description: "Synthetic ecommerce database — 5K customers, 20K orders"
    db_env: POSTGRES_DB
    db_host_env: POSTGRES_HOST
    db_port_env: POSTGRES_PORT
    semantic_dir: sql/semantic
    suggested_questions:
      - "What is our revenue trend this year?"
      - "Who are our top customers by lifetime value?"
      - "Which customers are at risk of churning?"
      - "How are our marketing campaigns performing?"

  - id: insurance
    label: "🏥 Insurance"
    description: "Auto-insurance portfolio — policies, claims, premiums"
    db_env: POSTGRES_DB_INSURANCE
    db_host_env: POSTGRES_HOST_INSURANCE
    db_port_env: POSTGRES_PORT_INSURANCE
    semantic_dir: sql/insurance/semantic
    suggested_questions:
      - "What is our current loss ratio?"
      - "How many policies are in force?"
      - "Show earned premium trend"
      - "What is the average claim severity?"
```

### 1.3 — app/client_registry.py (קובץ חדש)

```python
"""
SEMA: client registry.

Loads available clients from config/clients.yaml and resolves the active
client from st.session_state. This is the single source of truth for
which client is selected — db.py and semantic.py both read from here
instead of from the SEMA_CLIENT env var.
"""
```

פונקציות לממש:

- `load_clients() -> list[dict]` — קורא `config/clients.yaml`, מחזיר רשימה
- `get_client_by_id(client_id: str) -> dict` — lookup לפי id, raise ValueError אם לא קיים
- `get_active_client() -> dict` — מחזיר את הלקוח לפי `st.session_state.get("active_client_id", "ecommerce")`

### 1.4 — app/db.py — connection דינמי לפי client_id

**הבעיה:** `@st.cache_resource` על פונקציה ללא פרמטרים = connection אחד לצמיתות.
**הפתרון:** Streamlit יוצר cache entry נפרד לכל ערך פרמטר — הוסף `client_id: str` כפרמטר.

שנה את `get_connection()` ו-`get_readonly_connection()`:

```python
from client_registry import get_client_by_id
import os

@st.cache_resource
def get_connection(client_id: str) -> "psycopg2.extensions.connection":
    client = get_client_by_id(client_id)
    return psycopg2.connect(
        host=os.environ.get(client["db_host_env"], "localhost"),
        port=os.environ.get(client["db_port_env"], "5432"),
        dbname=os.environ.get(client["db_env"], client_id + "_db"),
        user=os.environ.get("POSTGRES_USER", "sema_user"),
        password=os.environ.get("POSTGRES_PASSWORD", "sema_password"),
    )

@st.cache_resource
def get_readonly_connection(client_id: str) -> "psycopg2.extensions.connection":
    client = get_client_by_id(client_id)
    conn = psycopg2.connect(
        host=os.environ.get(client["db_host_env"], "localhost"),
        port=os.environ.get(client["db_port_env"], "5432"),
        dbname=os.environ.get(client["db_env"], client_id + "_db"),
        user=os.environ.get("POSTGRES_READONLY_USER", "sema_readonly"),
        password=os.environ.get("POSTGRES_READONLY_PASSWORD", "sema_readonly_pw"),
        options=f"-c statement_timeout={READONLY_TIMEOUT_MS}",
    )
    conn.autocommit = True
    return conn
```

עדכן את `run_query()` ו-`run_sql_readonly()` ו-`check_connection()` לקרוא
לגרסאות החדשות עם `client_id`:

```python
def _active_client_id() -> str:
    try:
        import streamlit as st
        return st.session_state.get("active_client_id", "ecommerce")
    except Exception:
        return "ecommerce"
```

השתמש ב-`_active_client_id()` בכל מקום שנדרש.

### 1.5 — app/agent/semantic.py — טעינה דינמית

הסר את ה-`SEMANTIC_DIR` הגלובלי שמחושב ב-import time.
שנה את `load_semantic_layer()` לחשב את הנתיב בזמן ריצה:

```python
from client_registry import get_active_client

def load_semantic_layer() -> list[dict]:
    client = get_active_client()
    semantic_dir = Path(__file__).resolve().parent.parent.parent / client["semantic_dir"]
    # שאר הלוגיקה זהה
```

### 1.6 — app/pages/admin.py (קובץ חדש — Streamlit page)

Streamlit מגלה קבצים ב-`app/pages/` אוטומטית כדפים נפרדים.

הדף יציג:
- כותרת `"⚙️ Client Management"`
- שורה של `st.columns(len(clients))` — כרטיסייה לכל לקוח
- כל כרטיסייה מכילה:
  - label + description מה-YAML
  - סטטוס חיבור: קרא `check_connection()` עם client_id הרלוונטי
  - מספר metrics: `len(load_semantic_layer())` עבור אותו לקוח
  - כפתור `"Switch to [label]"` — אם זה הלקוח הפעיל, הצג `"✓ Active"` במקום

לחיצה על Switch:
```python
st.session_state.active_client_id = client["id"]
st.session_state.messages = []
st.session_state.agent_history = []
st.session_state.history = []
st.rerun()
```

### 1.7 — app/components/sidebar.py — עדכון

- הצג את label הלקוח הפעיל במקום הטקסט הקשיח `"Synthetic E-Commerce Database"`
- ה-suggested questions יגיעו מ-`get_active_client()["suggested_questions"]`
  ולא מ-`query_router.SUGGESTED_QUESTIONS`
- הוסף כפתור `"⚙️ Manage clients"` — בלחיצה: `st.switch_page("pages/admin.py")`
- הוסף כפתור `"✦ New conversation"` — בלחיצה: נקה את כל ה-session state של השיחה ו-`st.rerun()`

---

## PHASE 2 — Floating Alerts Panel (פאנל אלרטים צף)

### הקשר

אנחנו מוסיפים לוח אלרטים פרואקטיבי — פאנל צף בצד **ימין** של המסך (לא ה-sidebar הרגיל),
שנפתח כ-dropdown בלחיצה. הוא מציג התראות על חריגות במטריקות, ורץ ישירות מול ה-DB
ללא מעבר דרך הסוכן.

### 2.1 — הוסף alerts לקבצי ה-YAML

**sql/semantic/revenue.yaml** — הוסף את השדה הבא (לאחר `examples`):

```yaml
alerts:
  - id: revenue_mom_drop
    label: "Revenue Drop MoM"
    severity: critical
    condition_column: mom_pct_change
    condition_operator: "<"
    condition_value: -8
    sql: |
      WITH monthly AS (
        SELECT DATE_TRUNC('month', order_date) AS month,
               SUM(total_amount) AS revenue
        FROM orders WHERE status = 'completed'
        GROUP BY 1 ORDER BY 1 DESC LIMIT 2
      ),
      ranked AS (
        SELECT revenue, ROW_NUMBER() OVER (ORDER BY month DESC) AS rn FROM monthly
      )
      SELECT ROUND(
        (MAX(CASE WHEN rn=1 THEN revenue END) - MAX(CASE WHEN rn=2 THEN revenue END))
        / NULLIF(MAX(CASE WHEN rn=2 THEN revenue END), 0) * 100
      , 1) AS mom_pct_change
      FROM ranked
    message_template: "Revenue ירד {value}% MoM — חריג מעל ל-8%"
```

**sql/semantic/churn_risk.yaml** — הוסף:

```yaml
alerts:
  - id: churn_risk_count
    label: "At-Risk Customers"
    severity: warning
    condition_column: at_risk_count
    condition_operator: ">"
    condition_value: 300
    sql: |
      SELECT COUNT(*) AS at_risk_count
      FROM (
        SELECT customer_id, MAX(order_date) AS last_order
        FROM orders WHERE status = 'completed'
        GROUP BY customer_id
      ) t
      WHERE last_order <= (
        SELECT MAX(order_date) FROM orders WHERE status='completed'
      ) - INTERVAL '90 days'
    message_template: "{value} לקוחות ב-churn risk — מעל לסף 300"

  - id: churn_risk_vip
    label: "VIP Churn Risk"
    severity: critical
    condition_column: high_value_at_risk
    condition_operator: ">"
    condition_value: 50
    sql: |
      SELECT COUNT(*) AS high_value_at_risk
      FROM (
        SELECT customer_id, MAX(order_date) AS last_order, SUM(total_amount) AS ltv
        FROM orders WHERE status='completed'
        GROUP BY customer_id
      ) t
      WHERE last_order <= (
        SELECT MAX(order_date) FROM orders WHERE status='completed'
      ) - INTERVAL '90 days'
        AND ltv > 500
    message_template: "{value} לקוחות VIP ב-churn risk (LTV > $500)"
```

**sql/semantic/aov.yaml** — הוסף:

```yaml
alerts:
  - id: aov_mom_drop
    label: "AOV Drop MoM"
    severity: warning
    condition_column: mom_aov_change
    condition_operator: "<"
    condition_value: -5
    sql: |
      WITH monthly AS (
        SELECT DATE_TRUNC('month', order_date) AS month,
               AVG(total_amount) AS aov
        FROM orders WHERE status = 'completed'
        GROUP BY 1 ORDER BY 1 DESC LIMIT 2
      ),
      ranked AS (
        SELECT aov, ROW_NUMBER() OVER (ORDER BY month DESC) AS rn FROM monthly
      )
      SELECT ROUND(
        (MAX(CASE WHEN rn=1 THEN aov END) - MAX(CASE WHEN rn=2 THEN aov END))
        / NULLIF(MAX(CASE WHEN rn=2 THEN aov END), 0) * 100
      , 1) AS mom_aov_change
      FROM ranked
    message_template: "AOV ירד {value}% MoM"
```

**sql/semantic/active_customers.yaml** — הוסף:

```yaml
alerts:
  - id: active_customers_low
    label: "Active Customers Low"
    severity: warning
    condition_column: active_count
    condition_operator: "<"
    condition_value: 400
    sql: |
      SELECT COUNT(DISTINCT customer_id) AS active_count
      FROM orders
      WHERE status = 'completed'
        AND order_date > (
          SELECT MAX(order_date) FROM orders WHERE status='completed'
        ) - INTERVAL '90 days'
    message_template: "רק {value} לקוחות פעילים ב-90 יום האחרונים"
```

### 2.2 — app/components/alerts_engine.py (קובץ חדש)

```python
"""
SEMA: alerts engine.

Scans semantic YAML files for `alerts` entries, runs each SQL directly
against the read-only connection, evaluates the condition, and returns a
list of triggered alerts — sorted critical-first.

Decoupled from the agent: runs without Claude, like a scheduled check.
Cached for 2 minutes so it doesn't re-query on every Streamlit rerun.
"""
```

פונקציה ראשית: `def evaluate_all_alerts() -> list[dict]`

מעטפת ב: `@st.cache_data(ttl=120)`

לוגיקה:
1. קרא את כל ה-YAMLs דרך `load_semantic_layer()` (כבר קיים ב-semantic.py)
2. לכל metric שמכיל שדה `alerts`:
   - לכל alert entry: הרץ את ה-`sql` דרך `run_sql_readonly()`
   - קח את הערך מהעמודה `condition_column` בשורה הראשונה
   - בצע את ה-condition: `condition_column condition_operator condition_value`
     parse פשוט — תשתמש ב-`operator` module של Python (`lt`, `gt`, `le`, `ge`, `eq`, `ne`)
   - אם condition מתקיים — הוסף לרשימה:
     ```python
     {
       "id": alert["id"],
       "metric_label": metric["label"],
       "alert_label": alert["label"],
       "severity": alert["severity"],  # "critical" | "warning"
       "message": alert["message_template"].replace("{value}", str(value)),
       "value": value,
     }
     ```
3. עטוף כל alert בנפרד ב-try/except — alert שנכשל נדלג עליו ב-silence
4. מיין: `critical` ראשון, אחרי כן `warning`
5. החזר את הרשימה

### 2.3 — app/components/alerts_panel.py (קובץ חדש)

```python
"""
SEMA: floating right-side alerts panel.

Rendered as a fixed-position HTML/CSS/JS component — Streamlit has no
native right sidebar. The panel is a bell-icon button (top-right corner)
that toggles a dropdown showing triggered alerts.
"""
```

פונקציה: `def render(alerts: list[dict]) -> None`

אם `len(alerts) == 0` — אל תרנדר כלום ו-return מיד.

בנה HTML string שלם בתוך Python ולאחר מכן `st.markdown(html, unsafe_allow_html=True)`.

**מבנה HTML/CSS/JS:**

```
[🔔 N]  ← כפתור trigger, position:fixed, top:1rem, right:1rem, z-index:9999
         N = מספר האלרטים, badge צהוב/אדום לפי severity הגבוהה ביותר

  ↕ click toggles:

┌────────────────────────────────┐  ← position:fixed, top:3.5rem, right:1rem
│ ⚡ Alerts (N)           [×]   │     width:320px, max-height:70vh
├────────────────────────────────┤     overflow-y:auto, z-index:9998
│ 🔴  VIP Churn Risk             │     border-radius:12px, box-shadow
│     73 לקוחות VIP ב-churn...   │
├────────────────────────────────┤
│ 🟡  At-Risk Customers          │
│     342 לקוחות ב-churn risk... │
└────────────────────────────────┘
```

**CSS:**
- כפתור trigger: `border-radius:50%`, `width:42px`, `height:42px`, `background:#fff`,
  `border:1px solid #e5e7eb`, `box-shadow:0 2px 8px rgba(0,0,0,0.1)`
- badge המספר: `position:absolute`, `top:-6px`, `right:-6px`, גודל 18px
  - אם יש critical: `background:#dc2626` (אדום)
  - אם רק warning: `background:#ca8a04` (צהוב כהה)
- כרטיסיית alert לפי severity:
  - critical: `background:#fee2e2`, `border-left:3px solid #dc2626`
  - warning: `background:#fef9c3`, `border-left:3px solid #ca8a04`
- צבעי טקסט ו-font-family יהיו עקביים עם `TOKENS` של SEMA
  (ייבא `from components.theme import TOKENS` ושתמש בהם ב-f-string)

**JS:**
```javascript
function toggleSemaAlerts() {
  const panel = document.getElementById('sema-alerts-panel');
  panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
}
```

### 2.4 — app/main.py — חיבור הפאנל

הוסף בתחילת הקובץ:
```python
from components.alerts_engine import evaluate_all_alerts
from components.alerts_panel import render as render_alerts
```

הוסף **מיד לאחר** `sidebar.render()`:
```python
active_alerts = evaluate_all_alerts()
render_alerts(active_alerts)
```

### 2.5 — app/components/styles.py — תיקון CSS

הוסף לסוף ה-`_CSS` template (לפני closing `</style>`):
```css
/* Ensure the floating alerts panel is not clipped by Streamlit containers */
.stApp { overflow: visible !important; }
section[data-testid="stAppViewContainer"] { overflow: visible !important; }
```

---

## PHASE 3 — Multi-Turn Conversation History

### הקשר

כרגע `agent.run()` מאתחל `messages = [{"role": "user", "content": question}]`
בכל קריאה — הסוכן לא זוכר שאלות קודמות. `st.session_state.messages` שומר
response dicts לתצוגה בלבד, לא בפורמט Claude API.

הפתרון: ניהול `agent_history` נפרד בפורמט Claude API, מועבר לסוכן בכל שאלה.

### 3.1 — app/agent/agent.py — קבל היסטוריה

שנה את חתימת `run()`:
```python
def run(question: str, history: list[dict] | None = None, client=None) -> dict:
```

שנה את בניית `messages`:
```python
MAX_HISTORY_TURNS = 10  # שמור לכל היותר 10 תורות אחרונות

prior = list(history or [])
# חתוך אם ההיסטוריה ארוכה מדי (כל תור = 2 entries)
if len(prior) > MAX_HISTORY_TURNS * 2:
    prior = prior[-(MAX_HISTORY_TURNS * 2):]

messages: list[dict] = prior + [{"role": "user", "content": question}]
```

שנה את `MAX_TOKENS` מ-2000 ל-4000 (שיחות עם היסטוריה צורכות יותר טוקנים).

### 3.2 — app/agent/prompts.py — ספר לסוכן שהוא בשיחה

הוסף בתחילת `SYSTEM_PROMPT`, לפני כל שאר ההוראות:

```
You are in a multi-turn conversation. The conversation history above may \
contain previous questions and answers. If the user's message is a \
follow-up ("break that down by category", "why did that happen?", \
"show me only the top 5", "compare that to last month"), read the history \
to understand what they're referring to before calling tools. Reuse SQL \
logic from prior turns rather than redefining metrics from scratch.
```

### 3.3 — app/wiring.py — העבר היסטוריה

שנה את חתימת `get_response()`:
```python
def get_response(question: str, history: list[dict] | None = None) -> dict:
```

העבר לסוכן:
```python
return agent.run(question, history=history)
```

בנתיב ה-fallback (rule-based router) — history לא רלוונטית, השאר כמו שהוא.

### 3.4 — app/main.py — נהל agent_history

**אתחול:**
```python
if "agent_history" not in st.session_state:
    st.session_state.agent_history = []
```

**בעת שאלה חדשה**, העבר את ההיסטוריה:
```python
response = get_response(question, history=st.session_state.agent_history)
```

**אחרי קבלת תשובה**, הוסף לשני ה-states:
```python
# State לתצוגה (קיים)
rtl = chat.is_rtl(question)
st.session_state.messages.append({"role": "user", "content": question, "rtl": rtl})
st.session_state.messages.append({"role": "assistant", "content": response, "rtl": rtl})
st.session_state.history.append(question)

# State לסוכן (חדש) — טקסט בלבד, לא response dict
st.session_state.agent_history.append({"role": "user", "content": question})
st.session_state.agent_history.append({
    "role": "assistant",
    "content": response.get("insight_text", "")
})
```

### 3.5 — app/components/chat.py — separator בין תורות

בפונקציה `render_messages()`, הוסף visual separator בין תורות (בין כל
`assistant` → `user` עוקבים):

```python
def render_messages(messages: list[dict]) -> None:
    for i, message in enumerate(messages):
        # הוסף divider לפני כל שאלת משתמש שאינה הראשונה
        if message["role"] == "user" and i > 0:
            st.markdown(
                '<hr style="border:none;border-top:1px solid #e5e7eb;margin:0.75rem 0;">',
                unsafe_allow_html=True,
            )
        rtl = message.get("rtl", False)
        if message["role"] == "user":
            render_user_message(message["content"], rtl)
        else:
            render_assistant_message(message["content"], rtl)
```

---

## סדר ביצוע חובה

```
Phase 1:
  1.1 → docker-compose.yml + .env.example
  1.2 → config/clients.yaml
  1.3 → app/client_registry.py
  1.4 → app/db.py
  1.5 → app/agent/semantic.py
        [בדוק: python -c "from agent.semantic import load_semantic_layer; print(load_semantic_layer())"]
  1.6 → app/pages/admin.py
  1.7 → app/components/sidebar.py
        [בדוק: הפעל Streamlit, עבור בין לקוחות]

Phase 2:
  2.1 → עדכן 4 קבצי YAML
  2.2 → app/components/alerts_engine.py
        [בדוק: python -c "from components.alerts_engine import evaluate_all_alerts; print(evaluate_all_alerts())"]
  2.3 → app/components/alerts_panel.py
  2.4 → app/main.py — חיבור
  2.5 → app/components/styles.py
        [בדוק: הפאנל מופיע, toggle עובד, לא חוסם את הסידבר]

Phase 3:
  3.1 → app/agent/agent.py
  3.2 → app/agent/prompts.py
  3.3 → app/wiring.py
  3.4 → app/main.py — agent_history
  3.5 → app/components/chat.py
        [בדוק: שאל שאלה → קבל תשובה → שאל "פרט לפי קטגוריה" → הסוכן מבין ההקשר]
```

---

## מה לא לגעת בו

- `app/agent/safety.py` — guardrails ה-SQL נשארים כמו שהם
- `app/agent/tools.py` — לוגיקת הכלים ללא שינוי
- `app/agent/response.py` — assembler ה-response ללא שינוי
- לוגיקת ה-RTL ב-`chat.py` (render_user_message, render_assistant_message)
- `sql/semantic/*.yaml` — **לא** למחוק fields קיימים, רק להוסיף `alerts`
- `data/` — קבצי הנתונים והסכמות

---

## בדיקות מינימליות לפני סיום

1. `docker compose up -d` — שני containers עולים על פורטים 5432 ו-5433
2. Admin page נטען, מציג שני לקוחות, Switch עובד
3. ה-sidebar מציג את שם הלקוח הפעיל ואת ה-questions שלו
4. פאנל האלרטים מופיע בצד ימין, toggle פותח/סוגר, כרטיסיות מוצגות בצבע הנכון
5. שיחה רב-תורנית: שאל → קבל תשובה → שאל follow-up שמתייחס לתשובה → הסוכן מבין

---

*פרומפט זה נכתב על בסיס קריאת הקוד הקיים ב-SEMA (גרסה יוני 2026).*
*אין להוסיף dependencies חדשים ללא הסבר.*
