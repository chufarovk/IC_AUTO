import os
from typing import Dict, Any

import httpx
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# --- Настройки ---
APP_URL = os.getenv("ADMIN_APP_URL", "http://app")
DB_URL = os.getenv("ADMIN_DB_URL")
POLL_SECONDS = int(os.getenv("ADMIN_POLL_SECONDS", "5"))
PAGE_SIZE = int(os.getenv("ADMIN_PAGE_SIZE", "500"))

# Fallback для старых переменных окружения
if not DB_URL:
    DB_USER = os.getenv("POSTGRES_USER")
    DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
    DB_SERVER = "db"  # Внутри Docker сети
    DB_PORT = os.getenv("POSTGRES_PORT", "5432")
    DB_NAME = os.getenv("POSTGRES_DB")
    DB_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_SERVER}:{DB_PORT}/{DB_NAME}"

engine = create_engine(DB_URL)


# --- Функции ---
def trigger_replenishment(warehouse_id: str = ""):
    """Отправляет POST-запрос для запуска оценки дефицита."""
    try:
        url = APP_URL.rstrip("/") + "/api/v1/trigger/internal-replenishment"
        headers = {"Content-Type": "application/json"}
        payload = {"warehouse_id": warehouse_id.strip()} if warehouse_id.strip() else None

        with httpx.Client() as client:
            response = client.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            st.success(f"Процесс успешно запущен! Статус: {response.status_code}")
            if response.text:
                try:
                    result = response.json()
                    st.json(result)
                except:
                    st.text(response.text)
    except httpx.HTTPStatusError as e:
        st.error(f"Ошибка при запуске процесса: {e.response.status_code} - {e.response.text}")
    except Exception as e:
        st.error(f"Критическая ошибка: {e}")


@st.cache_data(ttl=POLL_SECONDS)
def load_logs(minutes: int = 60, level: str = "Все", system: str = "Все",
              status: str = "Все", step_like: str = "", run_id: str = "", limit: int = None):
    """Загружает логи из базы данных с фильтрами."""
    try:
        if limit is None:
            limit = PAGE_SIZE

        where = []
        params: Dict[str, Any] = {"limit": limit, "mins": minutes}

        # окно по времени (PostgreSQL-совместимо)
        where.append("(COALESCE(ts, created_at) >= (NOW() AT TIME ZONE 'UTC') - make_interval(mins => :mins))")

        if level and level != "Все":
            where.append("(COALESCE(log_level, details->>'level') = :level)")
            params["level"] = level

        if system and system != "Все":
            where.append("(COALESCE(external_system, 'INTERNAL') = :system)")
            params["system"] = system

        if status and status != "Все":
            where.append("(COALESCE(status, 'INFO') = :status)")
            params["status"] = status

        if step_like:
            where.append("(COALESCE(step, '') ILIKE :step)")
            params["step"] = f"%{step_like}%"

        if run_id:
            where.append("(COALESCE(run_id, '') = :run_id)")
            params["run_id"] = run_id

        where_sql = " AND ".join(where) if where else "TRUE"
        sql = text(
            f"""
            SELECT
              COALESCE(ts, created_at) AS created_at,
              COALESCE(process_name, step) AS process_name,
              COALESCE(log_level, status) AS log_level,
              COALESCE(message, details->>'message') AS message,
              run_id, request_id, job_id, step, status, external_system,
              elapsed_ms, retry_count, payload_hash, details, payload
            FROM integration_logs
            WHERE {where_sql}
            ORDER BY COALESCE(ts, created_at) DESC
            LIMIT :limit
            """
        )

        df = pd.read_sql(sql, engine, params=params)

        # Отображаем время в Москве
        if not df.empty and "created_at" in df.columns:
            try:
                df["created_at"] = pd.to_datetime(df["created_at"]).dt.tz_localize(
                    "UTC"
                ).dt.tz_convert("Europe/Moscow")
            except Exception:
                pass
        return df
    except Exception as e:
        st.error(f"Не удалось загрузить логи из базы данных: {e}")
        return pd.DataFrame()


# --- Интерфейс ---
st.set_page_config(page_title="Панель Администратора - Integration Hub", layout="wide")

# Заголовок с информацией о подключениях
st.title("🔧 Панель Администратора")
st.caption(f"DB: {DB_URL.split('@')[1] if '@' in DB_URL else 'N/A'} | App: {APP_URL}")

# --- Секция Ручного Управления ---
st.header("Ручное Управление")
col1, col2 = st.columns(2)

with col1:
    warehouse_id = st.text_input("Склад ID (опционально):", placeholder="Например: Юрловский")
    if st.button("🚀 Запустить оценку дефицита", use_container_width=True):
        trigger_replenishment(warehouse_id)

with col2:
    st.button("📦 Запустить внешний заказ (МойСклад)", disabled=True, use_container_width=True)
    st.caption("Функционал в разработке")

st.divider()

# --- Секция Журнала Операций ---
st.header("📊 Журнал Операций")

# Фильтры
col1, col2, col3, col4 = st.columns(4)

with col1:
    minutes = st.number_input("Период (минут):", min_value=1, max_value=1440, value=60)

with col2:
    level_filter = st.selectbox("Уровень:", ["Все", "DEBUG", "INFO", "WARN", "ERROR"])

with col3:
    system_filter = st.selectbox("Система:", ["Все", "INTERNAL", "1C", "MOYSKLAD"])

with col4:
    status_filter = st.selectbox("Статус:", ["Все", "INFO", "SUCCESS", "ERROR", "STARTED", "COMPLETED"])

col5, col6 = st.columns(2)
with col5:
    step_filter = st.text_input("Поиск по шагу:", placeholder="Например: replenishment")

with col6:
    run_id_filter = st.text_input("Run ID:", placeholder="Фильтр по конкретному запуску")

if st.button("🔄 Обновить логи"):
    st.cache_data.clear()

# Загрузка логов с фильтрами
logs_df = load_logs(
    minutes=minutes,
    level=level_filter,
    system=system_filter,
    status=status_filter,
    step_like=step_filter,
    run_id=run_id_filter
)

if not logs_df.empty:
    st.dataframe(logs_df, use_container_width=True)
    st.caption(f"Показано {len(logs_df)} записей за последние {minutes} минут")
else:
    st.warning("Логи отсутствуют или не удалось их загрузить за указанный период.")

