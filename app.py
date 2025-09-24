# app.py — Матвей Спицын: портфолио + site-analytics (Supabase)

import time
import uuid
from datetime import datetime, timezone
from collections import Counter

import streamlit as st
import streamlit.components.v1 as components
from supabase import create_client

# ===========================
# Общая настройка страницы
# ===========================
st.set_page_config(
    page_title="Портфолио Матвея Спицына | Аналитик данных",
    page_icon="📊",
    layout="wide",
)

# ===========================
# Supabase client (URL/KEY из st.secrets)
# В Streamlit Cloud добавь их в Settings → Secrets
# ===========================
SB_URL = st.secrets["SUPABASE_URL"]
SB_KEY = st.secrets["SUPABASE_KEY"]
sb = create_client(SB_URL, SB_KEY)

# ===========================
# Бизнес-слой: Votes + Analytics (sessions/events/durations)
# ===========================

# --- Votes ---
def init_votes():
    # Таблицы ты уже создал SQL-скриптом в Supabase; тут ничего не нужно.
    pass

def add_vote(choice: str):
    sb.table("votes").insert({"choice": choice}).execute()

def get_counts():
    likes = sb.table("votes").select("id", count="exact", head=True).eq("choice", "like").execute().count or 0
    dislikes = sb.table("votes").select("id", count="exact", head=True).eq("choice", "dislike").execute().count or 0
    return likes, dislikes

# --- Analytics (sessions / events / durations) ---
def init_analytics():
    pass  # таблицы уже есть

def ensure_session():
    if "visitor_id" not in st.session_state:
        st.session_state.visitor_id = str(uuid.uuid4())
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
        sb.table("sessions").upsert(
            {"visitor_id": st.session_state.visitor_id, "session_id": st.session_state.session_id},
            on_conflict="session_id"
        ).execute()

def touch_session():
    sb.table("sessions").update({"last_seen": datetime.now(timezone.utc).isoformat()})\
        .eq("session_id", st.session_state.session_id).execute()

def log_event(page: str, event_type: str, meta: str = None):
    sb.table("events").insert({
        "visitor_id": st.session_state.visitor_id,
        "session_id": st.session_state.session_id,
        "page": page, "event_type": event_type, "meta": meta
    }).execute()

def add_time(page: str, seconds: int):
    # upsert по (session_id, page)
    existing = sb.table("durations").select("seconds").eq("session_id", st.session_state.session_id).eq("page", page).execute()
    if existing.data:
        cur = existing.data[0].get("seconds", 0) or 0
        sb.table("durations").update({"seconds": cur + int(seconds)})\
          .eq("session_id", st.session_state.session_id).eq("page", page).execute()
    else:
        sb.table("durations").insert({
            "session_id": st.session_state.session_id, "page": page, "seconds": int(seconds)
        }).execute()

def start_page_timer(current_page: str):
    """Фиксируем переходы и логируем page_view."""
    ensure_session(); touch_session()
    now = time.time()
    prev_page = st.session_state.get("current_page")
    prev_ts   = st.session_state.get("page_enter_ts")

    # Закрываем предыдущую страницу (если была)
    if prev_page and prev_ts is not None and prev_page != current_page:
        add_time(prev_page, int(max(0, now - prev_ts)))

    # Старт для текущей
    if prev_page != current_page:
        log_event(current_page, "page_view")
        st.session_state["current_page"]  = current_page
        st.session_state["page_enter_ts"] = now

def finalize_time_on_rerun():
    touch_session()

# Голосование и сессии — базовая инициализация
init_votes()
init_analytics()
ensure_session()
if "voted" not in st.session_state:
    st.session_state.voted = False
if "vote_choice" not in st.session_state:
    st.session_state.vote_choice = None

# ===========================
# CSS (левый край + чипсы + компактные списки)
# ===========================
st.markdown("""
<style>
.block-container{
    max-width:100% !important;
    padding-left:12px; padding-right:32px; padding-top:10px;
    margin-left:0 !important; margin-right:0 !important;
}
header[data-testid="stHeader"]{ background:transparent; }

.hero-subtitle{ font-size:1.08rem; opacity:.9; margin-top:-6px; }
.likes-wrap{ padding-top:16px; }

.chips{ display:flex; flex-wrap:wrap; gap:8px; margin-top:6px; }
.chip{
    display:inline-block; padding:6px 10px; line-height:1; white-space:nowrap;
    border:1px solid rgba(0,0,0,.12); border-radius:999px; font-size:.92rem;
    background:rgba(0,0,0,.03);
}
.section-title{ margin:10px 0 4px 0; }
.tight li{ margin:.28rem 1; }
</style>
""", unsafe_allow_html=True)

# ===========================
# Навигация
# ===========================
st.sidebar.title("Меню")
page = st.sidebar.radio(
    "Выберите раздел:",
    ["Главная", "Дашборды", "A/B-тесты", "Аналитика сайта", "Контакты"]
)

# ===========================
# helper: Кнопка «лог + открыть ссылку»
# ===========================
def log_and_open(label: str, url: str, page_name: str, event_name: str, key: str):
    """
    Одна кнопка: при клике логируем событие в Supabase и открываем ссылку в новой вкладке.
    """
    if st.button(label, type="primary", key=key):
        log_event(page_name, event_name)
        st.session_state["_redirect_url"] = url
        st.rerun()

    if st.session_state.get("_redirect_url"):
        components.html(
            f"""
            <script>window.open("{st.session_state["_redirect_url"]}", "_blank");</script>
            """,
            height=0, width=0
        )
        st.session_state["_redirect_url"] = None

# ===========================
# СТРАНИЦЫ
# ===========================

# --- Главная ---
if page == "Главная":
    start_page_timer("Главная")

    left, _ = st.columns([0.8, 0.2])
    with left:
        st.title("📊 Портфолио Матвея Спицына")
        st.markdown(
            "<div class='hero-subtitle'>Аналитик данных · SQL · Python · Power BI · A/B-тесты</div>",
            unsafe_allow_html=True
        )
        st.write(
            "Помогаю принимать решения на данных: быстрые дашборды, A/B-тесты и понятные отчёты. "
            "Фокус на скорости, прозрачности и измеримом бизнес-эффекте."
        )

    st.header("Обо мне")
    st.markdown("""
- 🎓 4 курс Сочинского госуниверситета («Цифровые технологии в аналитической деятельности»).
- 🧰 Стек: **SQL** (ClickHouse, PostgreSQL), **Python** (pandas, plotly, pingouin),
  **BI** (DataLens, Power BI, Tableau), **Airflow**.
- 🧪 Продуктовые метрики и эксперименты: **CR, ARPU/ARPPU, Retention, Stickiness**, t-test/χ², доверительные интервалы.
- 📊 Для продавца **Wildberries** собрал витрину и дашборд в DataLens — снизил время анализа с ~2 часов до **15 минут**.
- 🚀 Ищу стажировку/джуниор-роль аналитика. Быстро вхожу в домен, документирую гипотезы и результаты, держу фокус на бизнес-эффекте.
    """)

    st.markdown("<h4 class='section-title'>Навыки и инструменты</h4>", unsafe_allow_html=True)
    st.markdown(
        "<div class='chips'>"
        "<span class='chip'>SQL</span><span class='chip'>ClickHouse</span><span class='chip'>PostgreSQL</span>"
        "<span class='chip'>Python</span><span class='chip'>pandas</span><span class='chip'>plotly</span>"
        "<span class='chip'>Power BI</span><span class='chip'>DataLens</span><span class='chip'>Tableau</span>"
        "<span class='chip'>Airflow</span><span class='chip'>A/B-тесты</span><span class='chip'>Статистика</span>"
        "</div>",
        unsafe_allow_html=True
    )

    st.markdown("<h4 class='section-title'>Чем могу быть полезен</h4>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""
<ul class="tight">
<li>Дашборды под задачи бизнеса (DataLens/Power BI)</li>
<li>SQL-аналитика и регулярная отчётность</li>
<li>Подготовка/проведение <b>A/B-тестов</b>, интерпретация результатов</li>
<li>Быстрые прототипы гипотез и метрик</li>
</ul>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown("""
<ul class="tight">
<li>E-com, маркетплейсы, контент-продукты</li>
<li>Метрики роста: CR, ARPU/ARPPU, Retention, Stickiness</li>
<li>Гостиничный сегмент: ADR, RevPAR, TRevPAR</li>
<li>Инструменты: ClickHouse, Python, BI, Airflow</li>
</ul>
        """, unsafe_allow_html=True)

    # CTA: 3 «умные» кнопки (лог + переход)
    st.markdown("<h4 class='section-title'>Быстрая связь со мной</h4>", unsafe_allow_html=True)
    cta1, cta2, cta3 = st.columns([1.2, 1, 1.4])
    with cta1:
        log_and_open("📨 Открыть Telegram", "https://t.me/cldmatv",
                     page_name="Главная", event_name="tg_click", key="tg_main")
    with cta2:
        log_and_open("🐱 Открыть GitHub", "https://github.com/MSSAS",
                     page_name="Главная", event_name="gh_click", key="gh_main")
    with cta3:
        log_and_open("📄 Открыть резюме", "https://sochi.hh.ru/resume/b872d5b3ff0f3adc440039ed1f786c7a745332",
                     page_name="Главная", event_name="resume_click", key="cv_main")

    finalize_time_on_rerun()

# --- Дашборды ---
elif page == "Дашборды":
    start_page_timer("Дашборды")

    st.header("📈 Мои дашборды")
    st.write("Интерактивные дашборды для решения бизнес-задач.")

    tab1, tab2 = st.tabs(["Аварийные объекты ЖКХ", "Зарубежный маркетплейс"])
    with tab1:
        iframe_code = """
        <iframe title="Аварийные объекты ЖКХ" width="1700" height="900" src="https://datalens.yandex/8ddgy8naysj4u"></iframe>
        """
        components.html(iframe_code, height=800)
    with tab2:
        st.subheader("📊 Аналитика продаж — Зарубежный маркетплейс")
        st.write("Задача: анализ продаж, прибыли, AKB, среднего чека и рентабельности по регионам и сегментам.")
        st.link_button("📥 Скачать .pbix", "https://drive.google.com/drive/folders/1zlu_QaB6J96GlohndvQwuAnbmle2USGo?usp=sharing")
        col1, col2, col3 = st.columns([1,4,1])
        with col2:
            try:
                st.image("image/Аналитика_продаж.png", caption="Дашборд аналитики продаж", use_column_width=True)
            except Exception:
                st.info("Изображение не найдено. Помести файл в `image/Аналитика_продаж.png`")

    finalize_time_on_rerun()

# --- A/B-тесты ---
elif page == "A/B-тесты":
    start_page_timer("A/B-тесты")

    st.header("🧪 A/B-тест новой механики оплаты")
    st.subheader("Методология")
    st.write("""
- 📊 Метрики: CR, ARPU.
- 📐 Проверка нормальности; t-test и χ²-тест.
- 📈 Интерпретация p-value и доверительных интервалов.
    """)
    st.subheader("Результаты (пример)")
    st.write("""
- **A (контроль):** CR = 2.1%, ARPU = 1500 ₽  
- **B (новая механика):** CR = 2.3%, ARPU = 1550 ₽  
- **p-value (t-test ARPU):** 0.03 (< 0.05) — статистически значимо  
- **Итог:** новую механику — рекомендовано к внедрению
    """)
    st.link_button("Код на GitHub", "https://github.com/MSSAS/AB-test_payment")

    finalize_time_on_rerun()

# --- Аналитика сайта ---
elif page == "Аналитика сайта":
    start_page_timer("Аналитика сайта")

    st.header("📊 Аналитика сайта (Supabase)")

    # Голосование
    st.subheader("Оценка сайта")
    likes, dislikes = get_counts()
    total = likes + dislikes
    approval = (likes/total*100) if total else 0

    c1, c2, c3 = st.columns(3)
    with c1: st.metric("👍 Лайки", likes)
    with c2: st.metric("👎 Дизлайки", dislikes)
    with c3: st.metric("Одобрение", f"{approval:.0f}%")

    if not st.session_state.voted:
        b1, b2 = st.columns(2)
        with b1:
            if st.button("👍 Лайк", use_container_width=True):
                add_vote("like"); st.session_state.voted=True; st.session_state.vote_choice="like"; st.rerun()
        with b2:
            if st.button("👎 Дизлайк", use_container_width=True):
                add_vote("dislike"); st.session_state.voted=True; st.session_state.vote_choice="dislike"; st.rerun()
    else:
        st.success(f"Спасибо! Ваш выбор: **{'👍 Лайк' if st.session_state.vote_choice=='like' else '👎 Дизлайк'}**")

    st.divider()
    st.subheader("Посетители, сессии и события")

    # агрегаты из Supabase
    visitors = sb.table("sessions").select("visitor_id", count="exact", head=True).execute().count or 0
    sessions = sb.table("sessions").select("session_id", count="exact", head=True).execute().count or 0

    pv_rows = sb.table("events").select("page").eq("event_type", "page_view").execute().data
    pageviews = Counter([r["page"] for r in pv_rows])

    tg_clicks = sb.table("events").select("id", count="exact", head=True).eq("event_type","tg_click").execute().count or 0
    gh_clicks = sb.table("events").select("id", count="exact", head=True).eq("event_type","gh_click").execute().count or 0
    cv_clicks = sb.table("events").select("id", count="exact", head=True).eq("event_type","resume_click").execute().count or 0

    dur_rows = sb.table("durations").select("page,seconds").execute().data
    durations = {r["page"]: r["seconds"] for r in dur_rows}

    d1, d2, d3, d4 = st.columns(4)
    with d1: st.metric("Уникальные посетители", visitors)
    with d2: st.metric("Сессии", sessions)
    with d3: st.metric("Клики в Telegram", tg_clicks)
    with d4: st.metric("Клики GitHub", gh_clicks)

    e1, e2, e3 = st.columns(3)
    with e1: st.metric("Клики Резюме", cv_clicks)

    home_pv = pageviews.get("Главная", 0)
    ctr_tg = (tg_clicks / home_pv * 100) if home_pv else 0
    ctr_gh = (gh_clicks / home_pv * 100) if home_pv else 0
    ctr_cv = (cv_clicks / home_pv * 100) if home_pv else 0

    c1, c2, c3 = st.columns(3)
    with c1: st.metric("CTR Telegram (от Главной)", f"{ctr_tg:.1f}%")
    with c2: st.metric("CTR GitHub (от Главной)", f"{ctr_gh:.1f}%")
    with c3: st.metric("CTR Резюме (от Главной)", f"{ctr_cv:.1f}%")

    st.markdown("#### Время на страницах (суммарно)")
    cols = st.columns(5)
    pages_list = ["Главная", "Дашборды", "A/B-тесты", "Аналитика сайта", "Контакты"]
    for i, p in enumerate(pages_list):
        with cols[i % 5]:
            sec = int(durations.get(p, 0) or 0)
            mm, ss = divmod(sec, 60)
            st.metric(p, f"{mm:02d}:{ss:02d}")

    st.markdown("#### Ваша текущая сессия")
    st.code(f"visitor_id={st.session_state.visitor_id}\nsession_id={st.session_state.session_id}", language="text")

    finalize_time_on_rerun()

# --- Контакты ---
elif page == "Контакты":
    start_page_timer("Контакты")

    st.header("📬 Свяжитесь со мной")
    st.write("Открыт к предложениям о стажировке и работе!")
    st.write("- 📞 Телефон: +7 (938) 425-24-03")
    st.write("- ✉️ Email: sp1tsyn1@yandex.ru")
    st.write("- 🐱 GitHub: [github.com/MSSAS](https://github.com/MSSAS)")
    st.write("- 📱 Telegram: [@cldmatv](https://t.me/cldmatv)")

    finalize_time_on_rerun()
