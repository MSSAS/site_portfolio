# app.py — Матвей Спицын: портфолио + site-analytics (Supabase, 1-user-1-vote)

# === 1. Импорт и СРАЗУ set_page_config ===
import streamlit as st
st.set_page_config(
    page_title="Портфолио Матвея Спицына | Аналитик данных",
    page_icon="📊",
    layout="wide",
)

import time
import uuid
from datetime import datetime, timezone
from collections import Counter
from pathlib import Path
from urllib.parse import quote_plus, unquote_plus

import streamlit.components.v1 as components
from supabase import create_client
from streamlit_cookies_manager import EncryptedCookieManager

# ===========================
# Supabase client (URL/KEY из st.secrets)
# ===========================
SB_URL = st.secrets.get("SUPABASE_URL")
SB_KEY = st.secrets.get("SUPABASE_KEY")
if not SB_URL or not SB_KEY:
    st.error("Нет секретов SUPABASE_URL / SUPABASE_KEY. Задай их в Settings → Secrets.")
    st.stop()
sb = create_client(SB_URL, SB_KEY)

# ===========================
# Cookies: персистентный visitor_id (для 1-user-1-vote и сессий)
# ===========================
COOKIE_PASSWORD = st.secrets.get("COOKIE_PASSWORD", "dev-only-unsafe")
cookies = EncryptedCookieManager(prefix="msp_", password=COOKIE_PASSWORD)
if not cookies.ready():
    st.stop()

def get_or_set_visitor_id() -> str:
    vid = cookies.get("visitor_id")
    if not vid:
        vid = str(uuid.uuid4())
        cookies["visitor_id"] = vid
        cookies.save()
    return vid

# ===========================
# Бизнес-слой: Votes + Analytics (sessions/events/durations)
# ===========================

# --- Votes ---
def add_vote(choice: str) -> bool:
    """
    Пишем голос с voter_id из cookie. Возвращает True если голос учтён,
    False — если пользователь уже голосовал (уникальный индекс сработал).
    """
    try:
        sb.table("votes").insert({"choice": choice, "voter_id": st.session_state.visitor_id}).execute()
        return True
    except Exception:
        return False

def has_voted() -> bool:
    r = sb.table("votes").select("id").eq("voter_id", st.session_state.visitor_id).limit(1).execute()
    return bool(r.data)

def get_counts():
    likes = sb.table("votes").select("id", count="exact", head=True).eq("choice", "like").execute().count or 0
    dislikes = sb.table("votes").select("id", count="exact", head=True).eq("choice", "dislike").execute().count or 0
    return likes, dislikes

# --- Analytics (sessions / events / durations) ---
def ensure_session():
    # visitor_id — из куки
    if "visitor_id" not in st.session_state:
        st.session_state.visitor_id = get_or_set_visitor_id()
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
        sb.table("sessions").upsert(
            {"visitor_id": st.session_state.visitor_id, "session_id": st.session_state.session_id},
            on_conflict="session_id"
        ).execute()

def touch_session():
    sb.table("sessions").update({"last_seen": datetime.now(timezone.utc).isoformat()}) \
      .eq("session_id", st.session_state.session_id).execute()

def log_event(page: str, event_type: str, meta: str = None):
    sb.table("events").insert({
        "visitor_id": st.session_state.visitor_id,
        "session_id": st.session_state.session_id,
        "page": page, "event_type": event_type, "meta": meta
    }).execute()

def add_time(page: str, seconds: int):
    # upsert по (session_id, page)
    existing = sb.table("durations").select("seconds") \
        .eq("session_id", st.session_state.session_id).eq("page", page).execute()
    if existing.data:
        cur = existing.data[0].get("seconds", 0) or 0
        sb.table("durations").update({"seconds": cur + int(seconds)}) \
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
.tight li{ margin:.28rem 1; }  /* фикс опечатки */
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
# --- helper: логируем и открываем ссылку в НОВОЙ вкладке ---
def log_and_open(label: str, url: str, page_name: str, event_name: str, key: str):
    """
    1) По клику логируем событие в Supabase
    2) Кладём URL в session_state и делаем st.rerun()
    3) После ререндера через JS открываем URL в новой вкладке (текущая остаётся)
    """
    if st.button(label, type="primary", key=key):
        try:
            log_event(page_name, event_name, meta=url)
        finally:
            st.session_state["_newtab_url"] = url
            st.rerun()

    new_url = st.session_state.pop("_newtab_url", None)
    if new_url:
        # Откроет новую вкладку; текущая не трогаем
        components.html(
            f"""
            <script>
              try {{
                window.open("{new_url}", "_blank", "noopener,noreferrer");
              }} catch (e) {{}}
            </script>
            """,
            height=0, width=0
        )
        # Фолбэк-кнопка, если вдруг браузер заблокировал (редко)
        st.caption("Если новая вкладка не открылась, нажми 👉")
        st.link_button("Открыть ссылку", new_url)

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

    st.header("Обо мне")
    st.markdown("""
- 🎓 4 курс Сочинского госуниверситета («Цифровые технологии в аналитической деятельности»).
- 🧰 Стек: **SQL** (ClickHouse, PostgreSQL), **Python** (pandas, plotly, pingouin),
  **BI** (DataLens, Power BI, Tableau), **Airflow**.
- 📊 Метрики: **CR, ARPU/ARPPU, Retention, DAU/WAU/MAU, Stickiness, CAC**
- 🧪 Эксперементы: бизнес-аспект эксперемента, дизайн эксперемента (a/b): MDE, мощность, стат. значимость, стат. критерий, размер групп.
- 🔊 Проводил интервьюирование ключевых сотрудников для выявление требований к ЭДО.
- 🚀 Ищу стажировку/джуниор-роль аналитика данных.
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
    st.markdown("""
<ul class="tight">
<li>Дашборды под задачи бизнеса (DataLens/Power BI)</li>
<li>SQL-аналитика и регулярная отчётность</li>
<li>Подготовка/проведение <b>A/B-тестов</b>, интерпретация результатов</li>
<li>Быстрые прототипы гипотез и метрик</li>
</ul>
        """, unsafe_allow_html=True)

    # CTA: 3 «умные» кнопки (лог + переход)
    st.markdown("<h4 class='section-title'>Быстрая связь со мной</h4>", unsafe_allow_html=True)
    cta1, cta2, cta3 = st.columns([1, 1, 4])
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
        components.html(iframe_code, height=700)
    with tab2:
        st.subheader("📊 Аналитика продаж — Зарубежный маркетплейс")
        st.write("Задача: анализ продаж, прибыли, AKB, среднего чека и рентабельности по регионам и сегментам.")
        st.link_button("📥 Скачать .pbix", "https://drive.google.com/drive/folders/1zlu_QaB6J96GlohndvQwuAnbmle2USGo?usp=sharing")

        img_path = Path(__file__).parent / "assets" / "sales_dashboard.png"
        if img_path.exists():
            st.image(str(img_path), caption="Дашборд аналитики продаж", use_container_width=True)
        else:
            st.info("Изображение не найдено. Помести файл в `assets/sales_dashboard.png`")

    finalize_time_on_rerun()

# --- A/B-тесты ---
elif page == "A/B-тесты":
    start_page_timer("A/B-тесты")
    st.header("🧪 A/B-тесты")

    tab1, tab2 = st.tabs(["Стриминг: рекомендательная лента", "Платёжная механика"])

    # ============ TAB 1: СТРИМИНГ ============
    with tab1:
        st.subheader("Новая рекомендательная лента (видеостриминг)")

        # ===== 1) Два столбца: Бизнес-аспект и Дизайн =====
        colL, colR = st.columns(2, gap="large")
        with colL:
            st.markdown("### Бизнес-аспект")
            st.markdown("""
    **Проблема.** Низкая конверсия в старт просмотра с домашнего экрана.  
    **Гипотеза.** Новая рекомендательная лента увеличит долю пользователей, начавших ≥1 просмотр.  
    **Кому показываем.** Все реальные пользователи (Android/iOS/Web); исключаем ботов/QA/сотрудников.  
    **Метрики:**
    - **Primary:** per-user «начал ≥1 просмотр»
    - **Guardrails:** TTFP, Crash rate
    - **Secondary:** CTR, глубина, watch time, D+1

    **Критерии успеха.** p<0.01 (двусторонний), uplift ≥ +5% (MDE), guardrails без деградаций.
    """)
        with colR:
            st.markdown("### Дизайн эксперимента")
            st.markdown("""
    - **Единица рандомизации:** пользователь; **сплит:** 50/50 (sticky)
    - **Горизонт:** ≥ 14 дней (недельная сезонность)
    - **Порог и мощность:** α = 0.01, power = 0.90
    - **Подглядывания:** нет (одна финальная проверка)
    - **Контроль качества:** SRM-чек, фильтры экспозиции, sanity-срезы (платформа/когорты)
    - **Критерий:** z-тест двух долей; 99% ДИ (B−A, непуленный Wald)
    - **План трафика:** ~18–20k пользователей/группу с запасом на фильтры
    - **Stop-rules:** TTFP > +5% к базе, рост crash/rebuffer сверх SLA → стоп и RCA
    """)

        st.markdown("---")

        # ===== 2) Результат (кратко): 4 KPI =====
        pA, pB = 0.4049, 0.4262
        rel_uplift, abs_diff_pp = 0.0526, 2.13
        p_val = 1.069e-05
        ci_low_pp, ci_high_pp = 0.88, 3.38
        p_ttfp, p_crash = 0.8027, 0.6278
        srm_p = 0.002698

        k1, k2, k3, k4 = st.columns(4)
        with k1: st.metric("A → B (uplift)", f"{rel_uplift:.2%}")
        with k2: st.metric("Абсолютная разница", f"{abs_diff_pp:.2f} %")
        with k3: st.metric("p-value", f"{p_val:.2e}")
        with k4: st.metric("99% доверительный интервал", f"[{ci_low_pp:.2f}; {ci_high_pp:.2f}]")
        st.caption(f"Guardrails: TTFP p={p_ttfp:.4f}, Crash p={p_crash:.4f} · SRM p={srm_p:.4g}")
        # Финальный вердикт
        st.success("Вердикт: SUCCESS — раскатка 25%→50%→100% + пост-мониторинг.")
        st.markdown("---")

        # ===== 3) График + материалы =====
        g1, g2 = st.columns([1.15, 0.85])
        with g1:
            st.markdown("#### Динамика по дням")
            img_path = Path(__file__).parent / "assets" / "ab_streaming_daily.png"
            if img_path.exists():
                st.image(str(img_path), use_container_width=True, caption="Daily conversion (A vs B)")
            else:
                st.info("Добавь `assets/ab_streaming_daily.png` — график появится здесь.")
        with g2:
            st.markdown("#### Материалы")
            st.link_button("Код на GitHub", "https://github.com/MSSAS/abtest-streaming-homefeed") 

    with tab2:
        st.subheader("A/B-тест новой механики оплаты (на готовых данных)")
        st.markdown("##### Методология")
        st.write("""
- 📊 Метрики: CR, ARPU.
- 📐 Проверка нормальности; t-test и χ²-тест.
- 📈 Интерпретация p-value и доверительных интервалов.
        """)
        st.markdown("##### Результаты")
        st.write("""
- **A (контроль):** CR = 2.1%, ARPU = 1500 ₽  
- **B (новая механика):** CR = 2.3%, ARPU = 1550 ₽  
- **p-value (t-test ARPU):** 0.03 (< 0.05) — статистически значимо  
        """)
        st.success("Итог: SUCCESS — новую механику — рекомендовано к внедрению.")
        # твоя ссылка
        st.link_button("Код на GitHub", "https://github.com/MSSAS/AB-test_payment")

    finalize_time_on_rerun()


# --- Аналитика сайта ---
elif page == "Аналитика сайта":
    start_page_timer("Аналитика сайта")

    st.header("📊 Аналитика сайта (Supabase)")

    # Голосование (1-user-1-vote)
    st.subheader("Оценка сайта")
    likes, dislikes = get_counts()
    total = likes + dislikes
    approval = (likes/total*100) if total else 0

    c1, c2, c3 = st.columns(3)
    with c1: st.metric("👍 Лайки", likes)
    with c2: st.metric("👎 Дизлайки", dislikes)
    with c3: st.metric("Одобрение", f"{approval:.0f}%")

    already_voted = has_voted()
    b1, b2 = st.columns(2)
    with b1:
        if st.button("👍 Лайк", use_container_width=True, disabled=already_voted):
            if add_vote("like"):
                st.success("Спасибо за голос!")
                st.rerun()
            else:
                st.info("Вы уже голосовали.")
    with b2:
        if st.button("👎 Дизлайк", use_container_width=True, disabled=already_voted):
            if add_vote("dislike"):
                st.success("Спасибо за голос!")
                st.rerun()
            else:
                st.info("Вы уже голосовали.")

    st.divider()
    st.subheader("Как пользуются моим сайтом")

    iframe_code = """
        <iframe title="DataLens" width="1700" height="610" src="https://datalens.yandex/27osxw8nptnmn"></iframe>
        """
    components.html(iframe_code, height=615)

    st.markdown("#### Ваше время на страницах (суммарно)")
        # Время на страницах
    dur_rows = sb.table("durations").select("page,seconds").execute().data or []
    durations = {r["page"]: (r.get("seconds") or 0) for r in dur_rows if r.get("page")}
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