# SEMA — פרומפט לקלוד קוד: תת-שיחות על ווידג'טים

## הוראות פתיחה

לפני שאתה כותב שורת קוד אחת, קרא את כל הקבצים הבאים:

```
app/main.py
app/wiring.py
app/agent/agent.py
app/agent/prompts.py
app/components/chat.py
app/components/kpi_cards.py
app/components/charts.py
app/components/tables.py
app/components/actions.py
app/components/styles.py
app/components/theme.py
```

---

## מה אנחנו בונים

### הבעיה

כיום המשתמש יכול לשאול שאלות המשך — אך רק ברמה הכללית של השיחה.
אם קיבל תשובה עם ארבעה KPI cards, גרף, טבלה ושלוש המלצות —
אין לו דרך לשאול "מדוע הגרף הזה דווקא ירד?" או "ספר לי עוד על ההמלצה הזאת"
בלי שהסוכן יצטרך להבין מהקשר כללי לאיזה אלמנט הוא מתכוון.

### הפתרון: Context Injection

כל ווידג'ט בתשובה (KPI card, גרף, טבלה, המלצה) יקבל כפתור קטן `💬`.
לחיצה עליו מגדירה **widget context** — קונטקסט ממוקד שמוחדר לשאלת המשתמש הבאה.

המשתמש רואה "context chip" מעל שדה הקלט, יכול לשאול שאלה ספציפית,
ויכול בכל רגע לנקות את הקונטקסט ולחזור לשאלה כללית.

**דוגמה לזרימה:**
```
[תשובת SEMA]
  KPI: Revenue $1.2M ▼14%  [💬]  ← המשתמש לוחץ כאן
  KPI: Orders 3.2K ▲3%    [💬]
  [גרף]                    [💬]
  [טבלה]                   [💬]
  Recommended actions:
    ↗ Launch win-back campaign [💬]

[strip ממוקד מופיע מעל שדה הקלט]
┌─────────────────────────────────────────────┐
│ 💬 שואל על: Revenue KPI — $1.2M, ▼14% MoM  │ [×]
└─────────────────────────────────────────────┘
[  למה הירידה התרכזה בקטגוריה מסוימת?      ]
                                         [שלח]
```

הסוכן מקבל:
`"[Context: Revenue KPI — $1.2M, ▼14% MoM] למה הירידה התרכזה בקטגוריה מסוימת?"`

---

## שינויים נדרשים — לפי קובץ

### 1. app/main.py — ניהול widget_context ב-session state

**אתחול state חדש:**
```python
if "widget_context" not in st.session_state:
    st.session_state.widget_context = None
# widget_context הוא dict או None. מבנה:
# {
#   "type": "kpi" | "chart" | "table" | "action",
#   "label": str,          # כותרת תמציתית לתצוגה ב-chip
#   "agent_prefix": str,   # הטקסט שיוחדר לשאלה שנשלחת לסוכן
# }
```

**context chip מעל שדה הקלט:**

הוסף את הבלוק הבא **לפני** `st.chat_input(...)`:

```python
if st.session_state.widget_context:
    ctx = st.session_state.widget_context
    col_ctx, col_clear = st.columns([10, 1])
    with col_ctx:
        st.markdown(
            f'<div class="sema-ctx-chip">💬 שואל על: {ctx["label"]}</div>',
            unsafe_allow_html=True,
        )
    with col_clear:
        if st.button("×", key="clear_ctx", help="חזור לשאלה כללית"):
            st.session_state.widget_context = None
            st.rerun()
```

**הזרקת קונטקסט לפני שליחה לסוכן:**

בבלוק `if question:`, לפני קריאה ל-`get_response()`:

```python
agent_question = question
if st.session_state.widget_context:
    prefix = st.session_state.widget_context["agent_prefix"]
    agent_question = f"{prefix}\n\n{question}"
    # נקה את הקונטקסט אחרי שליחה — שאלה כללית הבאה תתחיל נקייה
    st.session_state.widget_context = None

response = get_response(agent_question, history=st.session_state.agent_history)
```

**agent_history:** שמור את `agent_question` (עם הפרפיקס) ב-`agent_history`,
אבל את `question` המקורי (ללא פרפיקס) ב-`st.session_state.messages` לתצוגה —
אין צורך שהמשתמש יראה את הפרפיקס הטכני.

```python
st.session_state.agent_history.append({"role": "user", "content": agent_question})
st.session_state.agent_history.append({"role": "assistant", "content": response.get("insight_text", "")})

rtl = chat.is_rtl(question)
st.session_state.messages.append({"role": "user", "content": question, "rtl": rtl})
st.session_state.messages.append({"role": "assistant", "content": response, "rtl": rtl})
```

---

### 2. app/components/chat.py — העבר message_index לרנדור

הפונקציה `render_messages()` קוראת ל-`render_assistant_message()`.
שנה כך שמועבר גם אינדקס ההודעה — נדרש ליצירת keys ייחודיים לכפתורים:

```python
def render_messages(messages: list[dict]) -> None:
    assistant_idx = 0
    for i, message in enumerate(messages):
        if message["role"] == "user" and i > 0:
            st.markdown('<hr style="border:none;border-top:1px solid #e5e7eb;margin:0.75rem 0;">', unsafe_allow_html=True)
        rtl = message.get("rtl", False)
        if message["role"] == "user":
            render_user_message(message["content"], rtl)
        else:
            render_assistant_message(message["content"], rtl, msg_idx=assistant_idx)
            assistant_idx += 1
```

שנה את חתימת `render_assistant_message()`:
```python
def render_assistant_message(response: dict, rtl: bool = False, msg_idx: int = 0) -> None:
```

העבר `msg_idx` לכל קריאה ל-`kpi_cards.render`, `charts`, `tables`, `actions`:
```python
kpi_cards.render(response["kpis"], msg_idx=msg_idx)

for chart_idx, chart_spec in enumerate(response.get("charts", [])):
    fig = charts.render(chart_spec)
    st.plotly_chart(fig, use_container_width=True)
    _chart_ctx_button(chart_spec, msg_idx=msg_idx, chart_idx=chart_idx)

if response.get("table") is not None:
    tables.render(response["table"], response.get("table_title"), rtl=rtl)
    _table_ctx_button(response.get("table_title"), response["table"], msg_idx=msg_idx)

if response.get("recommended_actions"):
    actions.render(response["recommended_actions"], msg_idx=msg_idx)
```

**פונקציות עזר פנימיות ב-chat.py:**

```python
def _set_widget_context(ctx: dict) -> None:
    """Set the widget context and trigger rerun."""
    st.session_state.widget_context = ctx
    st.rerun()


def _chart_ctx_button(spec: dict, msg_idx: int, chart_idx: int) -> None:
    label = spec.get("title", "גרף")
    kind_labels = {"line": "גרף קווי", "bar": "גרף עמודות", "donut": "גרף עוגה", "grouped_bar": "גרף עמודות מקובץ"}
    kind = kind_labels.get(spec.get("kind", ""), "גרף")
    if st.button(f"💬 שאל על הגרף", key=f"ctx_chart_{msg_idx}_{chart_idx}"):
        _set_widget_context({
            "type": "chart",
            "label": label,
            "agent_prefix": (
                f"[Context: The user is asking about a specific chart from the previous answer.\n"
                f"Chart title: '{label}', Type: {spec.get('kind','')}, "
                f"X-axis: {spec.get('x','')}, Y-axis: {spec.get('y','')}.\n"
                f"Focus your answer on this chart specifically.]"
            ),
        })


def _table_ctx_button(title: str | None, df, msg_idx: int) -> None:
    if df is None or (hasattr(df, 'empty') and df.empty):
        return
    label = title or "טבלת נתונים"
    n_rows = len(df) if hasattr(df, '__len__') else "?"
    if st.button(f"💬 שאל על הטבלה", key=f"ctx_table_{msg_idx}"):
        _set_widget_context({
            "type": "table",
            "label": f"{label} ({n_rows} שורות)",
            "agent_prefix": (
                f"[Context: The user is asking about a specific data table from the previous answer.\n"
                f"Table title: '{label}', Columns: {list(df.columns) if hasattr(df, 'columns') else 'unknown'}.\n"
                f"Focus your answer on this table specifically.]"
            ),
        })
```

---

### 3. app/components/kpi_cards.py — הוסף כפתור לכל card

שנה את חתימת `render()`:
```python
def render(kpis: list[dict], msg_idx: int = 0) -> None:
```

בתוך הלולאה, אחרי `st.markdown(...)` של הכרטיסייה, הוסף כפתור:

```python
with col:
    st.markdown(
        f"""<div class="sema-kpi" style="background:{bg};">
            <div class="sema-kpi-label" style="color:{label_color};">{kpi['label']}</div>
            <div class="sema-kpi-value">{value_str}</div>
            {delta_html}
        </div>""",
        unsafe_allow_html=True,
    )
    # כפתור ה-context — מתחת לכרטיסייה, בתוך אותו column
    if st.button("💬", key=f"ctx_kpi_{msg_idx}_{i}", help=f"שאל על {kpi['label']}"):
        # בנה agent_prefix תמציתי ומדויק
        delta_str = ""
        if "delta" in kpi:
            arrow = "▲" if kpi["delta"] >= 0 else "▼"
            delta_str = f", {arrow}{abs(kpi['delta']):.1f}% {kpi.get('delta_label','MoM')}"
        
        from components.chat import _set_widget_context  # import מקומי למנוע circular
        _set_widget_context({
            "type": "kpi",
            "label": f"{kpi['label']} — {value_str}{delta_str}",
            "agent_prefix": (
                f"[Context: The user is asking about a specific KPI from the previous answer.\n"
                f"KPI: {kpi['label']}, Value: {value_str}{delta_str}.\n"
                f"Focus your analysis on this metric specifically.]"
            ),
        })
```

**שים לב:** import מקומי (`from components.chat import _set_widget_context`) בתוך הפונקציה
מונע circular import. חלופה נקייה יותר: העבר callback כפרמטר לפונקציה.
בחר את הגישה שנראית לך נקייה יותר, אך הסבר את הבחירה בתגובה.

---

### 4. app/components/actions.py — כפתור "ספר עוד" לכל המלצה

שנה את חתימת `render()`:
```python
def render(actions: list[str], msg_idx: int = 0) -> None:
```

לכל action, הוסף כפתור קטן אחרי הכרטיסייה:

```python
def render(actions: list[str], msg_idx: int = 0) -> None:
    if not actions:
        return

    st.markdown('<div class="sema-actions-title">Recommended actions</div>', unsafe_allow_html=True)
    for i, action in enumerate(actions):
        col_action, col_btn = st.columns([9, 1])
        with col_action:
            st.markdown(
                f'<div class="sema-action"><span class="arrow">&#8599;</span>'
                f"<span>{html.escape(action)}</span></div>",
                unsafe_allow_html=True,
            )
        with col_btn:
            if st.button("💬", key=f"ctx_action_{msg_idx}_{i}", help="ספר לי עוד"):
                from components.chat import _set_widget_context
                _set_widget_context({
                    "type": "action",
                    "label": action[:60] + ("..." if len(action) > 60 else ""),
                    "agent_prefix": (
                        f"[Context: The user is asking about a specific recommended action from the previous answer.\n"
                        f"Action: '{action}'.\n"
                        f"Explain how to execute this, what results to expect, and what to measure.]"
                    ),
                })
```

---

### 5. app/agent/prompts.py — ספר לסוכן על קונטקסט ווידג'ט

הוסף לתחילת SYSTEM_PROMPT (אחרי ה-multi-turn paragraph שכבר קיים):

```
When the user's message begins with "[Context: ...]", that bracket is a \
machine-generated note telling you exactly which element from the previous \
answer they are asking about (a specific KPI, chart, table, or recommended \
action). Read it carefully and focus your answer on that element. Do not \
repeat or explain the context block itself — just use it to inform your \
analysis. After the closing bracket, the user's actual question begins.
```

---

### 6. app/components/styles.py — CSS לחלקים החדשים

הוסף ל-`_CSS` template:

```css
/* ---- Widget context chip (above chat input) ---- */
.sema-ctx-chip {
    background: $lav_tint;
    color: $primary_dark;
    border: 1px solid $primary;
    border-radius: 999px;
    padding: 0.35rem 1rem;
    font-size: 0.82rem;
    font-weight: 500;
    display: inline-block;
    margin-bottom: 0.4rem;
}

/* ---- KPI context button ---- */
div[data-testid="stButton"] button[kind="secondary"][data-testid*="ctx_kpi"],
div[data-testid="stButton"] button[kind="secondary"][data-testid*="ctx_chart"],
div[data-testid="stButton"] button[kind="secondary"][data-testid*="ctx_table"],
div[data-testid="stButton"] button[kind="secondary"][data-testid*="ctx_action"] {
    background: transparent;
    border: none;
    color: $muted;
    font-size: 0.78rem;
    padding: 0.1rem 0.3rem;
    min-height: unset;
    width: auto;
}
div[data-testid="stButton"] button[kind="secondary"][data-testid*="ctx_kpi"]:hover,
div[data-testid="stButton"] button[kind="secondary"][data-testid*="ctx_chart"]:hover,
div[data-testid="stButton"] button[kind="secondary"][data-testid*="ctx_table"]:hover,
div[data-testid="stButton"] button[kind="secondary"][data-testid*="ctx_action"]:hover {
    color: $primary;
    background: $lav_tint;
}
```

**שים לב:** ה-CSS selector לעיל הוא best-effort — Streamlit משנה class names בין גרסאות.
בדוק בדפדפן (DevTools → Inspect) שהכפתורים מסוגלים לתפוס את הסלקטור, ועדכן בהתאם.
גישה אמינה יותר: עטוף כל כפתור context ב-div עם class ידני דרך `st.markdown` + `components.html`.

---

## מה **לא** לגעת בו

- `app/agent/tools.py` — ללא שינוי
- `app/agent/safety.py` — ללא שינוי
- `app/agent/semantic.py` — ללא שינוי
- לוגיקת ה-RTL ב-`chat.py`
- `alerts_engine.py` / `alerts_panel.py` אם קיימים
- `app/pages/admin.py` אם קיים

---

## סדר ביצוע

```
1. app/agent/prompts.py     — הוסף paragraph על [Context:] blocks
2. app/main.py              — אתחול widget_context, context chip, הזרקה לשאלה
3. app/components/chat.py   — msg_idx, _set_widget_context, _chart_ctx_button, _table_ctx_button
4. app/components/kpi_cards.py — כפתור 💬 לכל KPI
5. app/components/actions.py   — כפתור 💬 לכל המלצה
6. app/components/styles.py    — CSS לחלקים החדשים
```

---

## בדיקות מינימליות לפני סיום

1. שאל שאלה ← קבל תשובה עם KPI + גרף + טבלה + המלצות
2. לחץ 💬 על KPI card — context chip מופיע מעל שדה הקלט
3. שאל "למה?" ← הסוכן עונה ספציפית על ה-KPI הזה
4. לחץ × — chip נעלם, השאלה הבאה כללית
5. לחץ 💬 על המלצה ← context chip עם טקסט ההמלצה
6. שאל "איך מיישמים את זה?" ← הסוכן עונה על ההמלצה הספציפית
7. וודא: לחיצה על 💬 בהודעה **ישנה** עובדת נכון (keys ייחודיים לפי msg_idx)

---

## הערה על circular imports

`kpi_cards.py` ו-`actions.py` יצטרכו לגשת ל-`_set_widget_context` מ-`chat.py`.
שתי גישות אפשריות — בחר אחת ותסביר:

**גישה A — import מקומי בתוך הפונקציה** (פשוט, מקובל ב-Python):
```python
def render(...):
    from components.chat import _set_widget_context
    ...
```

**גישה B — callback כפרמטר** (נקייה יותר, ללא coupling):
```python
def render(kpis, msg_idx=0, on_context=None):
    ...
    if on_context and st.button("💬", ...):
        on_context({...})
```
ב-`chat.py` קוראים: `kpi_cards.render(kpis, msg_idx=msg_idx, on_context=_set_widget_context)`

גישה B מועדפת — מעמידה את `kpi_cards` כ-pure renderer ללא תלות ב-chat.

*פרומפט זה נכתב על בסיס קריאת הקוד הקיים ב-SEMA (גרסה יוני 2026).*
