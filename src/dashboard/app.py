"""A practical, plain-language view of the project's synthetic marketplace data."""

import os
from datetime import timedelta

import altair as alt
import pandas as pd
import streamlit as st
from dagster import DagsterInstance

from dashboard.data import date_bounds, get_products, query_freshness, query_metrics, query_visuals
from operations.config import connect_database

st.set_page_config(
    page_title="Market Pulse — обзор магазина",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(
    """<style>
    .stApp {background: #f7f7f4; color: #202b27;}
    .block-container {max-width: 1450px; padding-top: 2rem; padding-bottom: 4rem;}
    [data-testid="stSidebar"] {background: #eff2ec; border-right: 1px solid #e1e7dd;}
    h1, h2, h3 {letter-spacing: -0.035em; color: #172c25;}
    h1 {font-weight: 750 !important;}
    .eyebrow {font-size: .72rem; font-weight: 800; letter-spacing: .16em;
              color: #408467; text-transform: uppercase; margin-bottom: .5rem;}
    .hero {background: #173d30; color: #f7faf5; border-radius: 20px;
           padding: 2rem 2.3rem; margin: .5rem 0 1.7rem;}
    .hero h2 {color: #fff; margin: 0 0 .5rem; font-size: 2rem;}
    .hero p {color: #d1e6d6; max-width: 760px; margin: 0; line-height: 1.6;}
    div[data-testid="stMetric"] {background: #fff; border: 1px solid #e7ece5;
       border-radius: 16px; padding: 1.1rem 1.2rem; min-height: 120px;}
    div[data-testid="stMetricLabel"], div[data-testid="stMetricLabel"] p {
       color: #63756a !important;}
    div[data-testid="stMetricValue"] {color: #183d30; font-weight: 700; font-size: 1.7rem;}
    .section-note {color: #68796f; font-size: .95rem; margin: -.3rem 0 1.1rem;}
    .info-box {background: #eef4eb; border: 1px solid #dae8d8; border-radius: 14px;
      padding: 1rem 1.2rem; color: #345443; line-height: 1.55; margin: .5rem 0 1rem;}
    .stTabs [data-baseweb="tab-list"] {gap: 1.5rem;}
    .stTabs [data-baseweb="tab"] {font-weight: 650;}
    </style>""",
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="eyebrow">✦ Market Pulse &nbsp; / &nbsp; демо магазина</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="hero"><h2>Ваш магазин, понятнее.</h2>'
    "<p>Продажи, реклама и остатки в одном месте. Выберите период и товары слева, "
    "чтобы увидеть, что происходит в магазине и на что стоит обратить внимание.</p></div>",
    unsafe_allow_html=True,
)
st.caption("Демонстрация на синтетических данных · ₽ · даты продаж и рекламы в UTC")
schema = os.getenv("DBT_SCHEMA", "analytics")


def money(value):
    return f"{value:,.0f} ₽".replace(",", " ") if value is not None else "Нет данных"


def line_chart(frame, x, y, color="#31866a"):
    return (
        alt.Chart(frame)
        .mark_area(
            line={"color": color, "strokeWidth": 3},
            color=alt.Gradient(
                gradient="linear",
                stops=[
                    alt.GradientStop(color="#d4eadd", offset=0),
                    alt.GradientStop(color="#f8fbf8", offset=1),
                ],
                x1=0,
                x2=0,
                y1=0,
                y2=1,
            ),
        )
        .encode(
            x=alt.X(f"{x}:T", title=None, axis=alt.Axis(format="%d.%m")),
            y=alt.Y(f"{y}:Q", title=None),
            tooltip=[
                alt.Tooltip(f"{x}:T", title="Дата", format="%d.%m.%Y"),
                alt.Tooltip(f"{y}:Q", title=y, format=",.0f"),
            ],
        )
        .properties(height=240)
    )


try:
    with connect_database() as conn:
        products = get_products(conn, schema)
        lower, upper = date_bounds(conn, schema)
        if lower is None or upper is None:
            st.warning("Пока нет данных. Запустите загрузку и dbt build, затем обновите страницу.")
            st.stop()
        labels = {ident: f"{name} · {sku}" for ident, sku, name in products}
        st.sidebar.markdown("### Настройте обзор")
        st.sidebar.caption("Фильтры помогают посмотреть весь магазин или отдельные товары.")
        dates = st.sidebar.date_input(
            "Период",
            value=(lower, upper),
            min_value=lower,
            max_value=upper,
            help="Даты заказов и рекламных расходов в UTC. На последние остатки период не влияет.",
        )
        selected = st.sidebar.multiselect(
            "Товары",
            options=list(labels),
            format_func=labels.get,
            placeholder="Все товары",
            help="Оставьте поле пустым, чтобы увидеть все товары.",
        )
        st.sidebar.markdown("---")
        st.sidebar.caption(
            "✦ Учебный проект: все данные сгенерированы и не относятся к реальным покупателям."
        )
        if not isinstance(dates, (tuple, list)) or len(dates) != 2:
            st.info("Выберите начало и конец периода в меню слева.")
            st.stop()
        if dates[0] > dates[1]:
            st.error("Начало периода должно быть раньше конца.")
            st.stop()
        sales, ads, stocks = query_metrics(conn, schema, dates[0], dates[1], selected or None)
        daily_sales, daily_ads, top_products = query_visuals(
            conn, schema, dates[0], dates[1], selected or None
        )
        try:
            freshness = query_freshness(
                conn, timedelta(hours=float(os.getenv("FRESHNESS_MAX_HOURS", "24")))
            )
        except Exception:
            conn.rollback()
            freshness = None
except (Exception, SystemExit) as exc:
    if isinstance(exc, SystemExit):
        raise
    st.error(
        f"Не удалось открыть данные ({type(exc).__name__}). "
        "Проверьте PostgreSQL и запустите dbt build."
    )
    st.stop()

count, gross, aov = sales
available_stock = [row[2] for row in stocks if row[2] is not None]
st.markdown("### Главное за выбранный период")
st.markdown(
    '<p class="section-note">Быстрый взгляд на продажи и расходы. '
    "Наведите курсор на ⓘ, чтобы узнать больше.</p>",
    unsafe_allow_html=True,
)
cols = st.columns(4)
cols[0].metric(
    "Стоимость заказов",
    money(gross),
    help="Сумма всех оформленных заказов, включая отменённые. Это не чистая выручка.",
)
cols[1].metric(
    "Заказы",
    f"{count:,}".replace(",", " "),
    help="Количество оформленных заказов за выбранный период, включая отменённые.",
)
cols[2].metric(
    "Средний заказ",
    money(aov),
    help="Стоимость всех заказов, делённая на их количество. Включает отмены.",
)
cols[3].metric(
    "Расходы на рекламу",
    money(ads[0]),
    help="Сумма рекламных расходов за выбранный период. Не показывает прибыль или окупаемость.",
)
st.markdown(
    '<div class="info-box"><b>Как читать цифры:</b> стоимость заказов включает отмены. '
    "Чистую выручку пока нельзя рассчитать без данных о возвратах, а окупаемость рекламы "
    "(ROAS) — без связи заказов с рекламными кампаниями.</div>",
    unsafe_allow_html=True,
)

tab_sales, tab_ads, tab_stock, tab_health = st.tabs(
    ["📈 Продажи", "✦ Реклама", "▦ Остатки", "◉ Состояние данных"]
)
with tab_sales:
    st.subheader("Как менялись продажи")
    st.markdown(
        '<p class="section-note">Посмотрите, в какие дни покупатели оформляли больше заказов. '
        "Сумма включает отмены.</p>",
        unsafe_allow_html=True,
    )
    if daily_sales:
        df = pd.DataFrame(daily_sales, columns=["Дата", "Заказы", "Стоимость заказов, ₽"])
        df["Стоимость заказов, ₽"] = pd.to_numeric(df["Стоимость заказов, ₽"])
        df["Дата"] = pd.to_datetime(df["Дата"])
        left, right = st.columns(2)
        with left:
            st.markdown("**Стоимость заказов по дням**")
            st.altair_chart(line_chart(df, "Дата", "Стоимость заказов, ₽"), width="stretch")
        with right:
            st.markdown("**Количество заказов по дням**")
            st.altair_chart(line_chart(df, "Дата", "Заказы"), width="stretch")
    else:
        st.info("За выбранный период заказов нет. Попробуйте изменить фильтры.")
    st.subheader("Какие товары заказывают на большую сумму")
    st.caption("Топ-10 по стоимости оформленных заказов за выбранный период; отмены включены.")
    if top_products:
        df = pd.DataFrame(top_products, columns=["Артикул", "Товар", "Заказы", "Стоимость, ₽"])
        df["Стоимость, ₽"] = pd.to_numeric(df["Стоимость, ₽"])
        df["Товар"] = df["Товар"] + " · " + df["Артикул"]
        chart = (
            alt.Chart(df)
            .mark_bar(color="#398b6b", cornerRadiusEnd=5)
            .encode(
                y=alt.Y("Товар:N", sort="-x", title=None),
                x=alt.X("Стоимость, ₽:Q", title="Стоимость заказов, ₽"),
                tooltip=["Товар:N", "Заказы:Q", alt.Tooltip("Стоимость, ₽:Q", format=",.0f")],
            )
            .properties(height=max(150, len(df) * 36))
        )
        st.altair_chart(chart, width="stretch")
    else:
        st.info("Для выбранных фильтров пока нет заказов.")

with tab_ads:
    st.subheader("Сколько вы тратите на рекламу")
    st.markdown(
        '<p class="section-note">График помогает заметить дни с повышенными расходами. '
        "Он не показывает, какие продажи принесла реклама.</p>",
        unsafe_allow_html=True,
    )
    if daily_ads:
        df = pd.DataFrame(daily_ads, columns=["Дата", "Расходы, ₽"])
        df["Дата"] = pd.to_datetime(df["Дата"])
        df["Расходы, ₽"] = pd.to_numeric(df["Расходы, ₽"])
        st.altair_chart(line_chart(df, "Дата", "Расходы, ₽"), width="stretch")
    else:
        st.info("За выбранный период расходов на рекламу нет.")
    st.info(
        "Окупаемость рекламы (ROAS) пока недоступна: в источнике нет связи заказов с кампаниями."
    )

with tab_stock:
    st.subheader("Что происходит с остатками")
    st.markdown(
        '<p class="section-note">Последний известный остаток по каждому товару. '
        "Фильтр товаров действует, выбранный период — нет.</p>",
        unsafe_allow_html=True,
    )
    cols = st.columns(2)
    cols[0].metric(
        "Товаров на складе",
        f"{sum(available_stock):,}".replace(",", " ") if available_stock else "Нет данных",
        help="Сумма последних доступных снимков по складам. Даты снимков могут различаться.",
    )
    coverage = [float(row[3]) for row in stocks if row[3] is not None]
    cols[1].metric(
        "Товаров с запасом до 30 дней",
        sum(1 for v in coverage if v <= 30) if coverage else "Нет оценки",
        help="Оценка по среднему спросу за 30 дней. Это не прогноз; товары без оценки не включены.",
    )
    if len(available_stock) < len(stocks):
        st.warning("Для части товаров нет снимков остатков, поэтому сумма неполная.")
    stock_df = pd.DataFrame(
        stocks,
        columns=[
            "ID",
            "Артикул",
            "Остаток",
            "Запас, дней",
            "Начальная дата снимка",
            "Последний снимок",
        ],
    )
    stock_df["Товар"] = stock_df["ID"].map(labels)
    if not stock_df.empty:
        stock_df["Запас, дней"] = pd.to_numeric(stock_df["Запас, дней"])
        ranked = stock_df.dropna(subset=["Запас, дней"]).sort_values("Запас, дней").head(10)
        if not ranked.empty:
            st.markdown("**Наименьший оценочный запас**")
            st.caption(
                "Сколько дней может хватить товара при среднем спросе за последние 30 дней; "
                "показаны товары с доступной оценкой."
            )
            chart = (
                alt.Chart(ranked)
                .mark_bar(color="#d89566", cornerRadiusEnd=5)
                .encode(
                    y=alt.Y("Товар:N", sort="x", title=None),
                    x=alt.X("Запас, дней:Q", title="Дней"),
                    tooltip=[
                        "Товар:N",
                        alt.Tooltip("Остаток:Q", title="Остаток, шт."),
                        alt.Tooltip("Запас, дней:Q", format=".1f"),
                    ],
                )
                .properties(height=max(150, len(ranked) * 36))
            )
            st.altair_chart(chart, width="stretch")
        with st.expander("Посмотреть остатки всех выбранных товаров"):
            st.dataframe(stock_df.drop(columns=["ID"]), hide_index=True, width="stretch")
    else:
        st.info("Нет товаров для выбранных фильтров.")

with tab_health:
    st.subheader("Когда данные обновлялись")
    st.markdown(
        '<p class="section-note">Здесь видно, завершилась ли последняя загрузка недавно. '
        "Это локальная диагностика, а не круглосуточный мониторинг.</p>",
        unsafe_allow_html=True,
    )
    if freshness is None:
        st.warning("Не удалось получить состояние загрузки. Проверьте таблицу raw.ingestion_state.")
    else:
        names = {
            "orders": "Заказы",
            "products": "Товары",
            "stocks": "Остатки",
            "advertising": "Реклама",
        }
        states = {
            "fresh": "Обновлено недавно",
            "stale": "Давно не обновлялось",
            "missing": "Ещё не загружено",
            "clock skew": "Проверьте время",
        }
        health = pd.DataFrame(
            freshness,
            columns=[
                "resource",
                "Последняя успешная загрузка",
                "Последнее изменение в источнике",
                "status",
            ],
        )
        health["Раздел"] = health["resource"].map(names)
        health["Состояние"] = health["status"].map(states)
        st.dataframe(
            health[
                [
                    "Раздел",
                    "Состояние",
                    "Последняя успешная загрузка",
                    "Последнее изменение в источнике",
                ]
            ],
            hide_index=True,
            width="stretch",
        )
    with st.expander("История запусков: технические подробности"):
        st.caption(
            "Dagster запускает загрузку, затем обновляет аналитические модели. "
            "Здесь отображаются последние 20 запусков."
        )
        try:
            with DagsterInstance.get() as instance:
                records = instance.get_run_records(limit=20)
            if not records:
                st.info("Запусков ещё нет.")
            else:
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "Запуск": record.dagster_run.run_id,
                                "Задача": record.dagster_run.job_name,
                                "Статус": record.dagster_run.status.value,
                                "Начало": pd.to_datetime(record.start_time, unit="s", utc=True)
                                if record.start_time
                                else None,
                                "Окончание": pd.to_datetime(record.end_time, unit="s", utc=True)
                                if record.end_time
                                else None,
                            }
                            for record in records
                        ]
                    ),
                    hide_index=True,
                    width="stretch",
                )
        except Exception:
            st.warning("История запусков недоступна. Проверьте DAGSTER_HOME и хранилище Dagster.")
