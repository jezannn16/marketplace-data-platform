"""Local Streamlit dashboard over the project's actual analytics models."""

import os
from datetime import timedelta

import pandas as pd
import streamlit as st
from dagster import DagsterInstance

from dashboard.data import date_bounds, get_products, query_freshness, query_metrics
from operations.config import connect_database

st.set_page_config(page_title="Marketplace Data Platform", layout="wide")
st.title("Marketplace Data Platform")
st.caption("Синтетические данные · суммы в RUB · даты заказов и рекламы — UTC")
schema = os.getenv("DBT_SCHEMA", "analytics")

try:
    with connect_database() as conn:
        products = get_products(conn, schema)
        lower, upper = date_bounds(conn, schema)
        if lower is None or upper is None:
            st.warning("В моделях пока нет данных. Выполните ingestion и dbt build.")
            st.stop()
        selected = st.sidebar.multiselect(
            "Товары",
            options=[row[0] for row in products],
            format_func=lambda value: next(
                f"{sku} — {name}" for ident, sku, name in products if ident == value
            ),
        )
        dates = st.sidebar.date_input(
            "Период продаж и рекламы (UTC)", value=(lower, upper), min_value=lower, max_value=upper
        )
        if not isinstance(dates, (tuple, list)) or len(dates) != 2:
            st.info("Выберите начало и конец периода.")
            st.stop()
        if dates[0] > dates[1]:
            st.error("Начало периода позже конца.")
            st.stop()
        sales, ads, stocks = query_metrics(conn, schema, dates[0], dates[1], selected or None)
        try:
            freshness = query_freshness(
                conn, timedelta(hours=float(os.getenv("FRESHNESS_MAX_HOURS", "24")))
            )
        except Exception:
            conn.rollback()
            freshness = None
        count, gross, aov = sales
        columns = st.columns(6)
        columns[0].metric(
            "Валовая стоимость заказов", f"{gross:,.2f} ₽" if gross is not None else "Нет данных"
        )
        columns[1].metric("Заказы", count)
        columns[2].metric(
            "Средний заказ (gross)", f"{aov:,.2f} ₽" if aov is not None else "Нет данных"
        )
        columns[3].metric("Реклама", f"{ads[0]:,.2f} ₽" if ads[0] is not None else "Нет данных")
        columns[4].metric("ROAS", "Недоступен")
        available_stock = [row[2] for row in stocks if row[2] is not None]
        columns[5].metric(
            "Остаток: последние снимки",
            f"{sum(available_stock):,}" if available_stock else "Нет данных",
        )
        if len(available_stock) < len(stocks):
            st.warning("Не для всех выбранных товаров есть снимки остатков; сумма неполная.")
        st.caption(
            "Gross включает отмены и не является признанной выручкой. "
            "Net revenue недоступна без возвратов; ROAS — без атрибуции заказов к кампаниям."
        )
        st.subheader("Последние известные остатки")
        st.caption(
            "Фильтр товаров применяется; период не меняет последние снимки. "
            "Даты складов могут различаться; покрытие — оценка спроса за 30 дней."
        )
        stock_df = pd.DataFrame(
            stocks,
            columns=[
                "product_id",
                "sku",
                "stock_quantity",
                "stock_coverage_days",
                "coverage_anchor_utc",
                "latest_snapshot_utc",
            ],
        )
        st.dataframe(stock_df, hide_index=True, width="stretch")
        st.subheader("Свежесть загрузки")
        st.caption(
            "Порог относится к последней успешной загрузке, а не к дате изменения данных. "
            "Это локальная диагностика, не production monitoring."
        )
        if freshness is None:
            st.warning("Состояние загрузки недоступно; проверьте raw.ingestion_state.")
        else:
            st.dataframe(
                pd.DataFrame(
                    freshness, columns=["resource", "last_success_at", "source_cursor", "status"]
                ),
                hide_index=True,
                width="stretch",
            )
except (Exception, SystemExit) as exc:
    if isinstance(exc, SystemExit):
        raise
    st.error(
        f"Не удалось прочитать данные или модели: {type(exc).__name__}. "
        "Проверьте PostgreSQL, конфигурацию и dbt build."
    )

st.subheader("Последние запуски Dagster")
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
                        "run_id": record.dagster_run.run_id,
                        "job": record.dagster_run.job_name,
                        "status": record.dagster_run.status.value,
                        "started_at": pd.to_datetime(record.start_time, unit="s", utc=True)
                        if record.start_time
                        else None,
                        "ended_at": pd.to_datetime(record.end_time, unit="s", utc=True)
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
    st.warning("История Dagster недоступна. Проверьте DAGSTER_HOME и доступ к хранилищу запусков.")
