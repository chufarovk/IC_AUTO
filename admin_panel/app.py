import os
import socket
from typing import Dict, Any

import httpx
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# --- Функции ---
def resolve_app_base_url() -> str:
    """Определяет базовый URL для подключения к приложению с фоллбеком."""
    url = os.getenv("ADMIN_APP_URL", "").strip()
    # если явно задан — пробуем как есть
    if url:
        return url

    # попытка резолва docker-сервиса "app"
    try:
        socket.gethostbyname("app")
        # app слушает внутри контейнера порт 80
        return "http://app"
    except Exception:
        pass

    # локальный фоллбек (когда admin запускают вне Docker)
    return "http://localhost:8000"

# --- Настройки ---
APP_BASE = resolve_app_base_url()
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
        url = APP_BASE.rstrip("/") + "/api/v1/trigger/internal-replenishment"
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


def create_logs_table():
    """Создает таблицу integration_logs через API приложения."""
    try:
        url = APP_BASE.rstrip("/") + "/admin/init_logs_table"
        headers = {"Content-Type": "application/json"}

        with httpx.Client() as client:
            response = client.post(url, headers=headers, timeout=30)
            response.raise_for_status()
            st.success("Таблица логов успешно создана!")
            st.rerun()
    except httpx.HTTPStatusError as e:
        st.error(f"Ошибка при создании таблицы: {e.response.status_code} - {e.response.text}")
    except Exception as e:
        st.error(f"Критическая ошибка при создании таблицы: {e}")


def fetch_logs_safe(params: dict):
    """
    Обёртка получения логов:
    - на успехе: возвращает pd.DataFrame
    - если таблицы нет: строку-сентинел 'TABLE_NOT_EXISTS'
    - на иных ошибках: строка 'ERROR: ...'
    """
    try:
        minutes = params.get("mins", 60)
        level = params.get("level", "Все")
        system = params.get("system", "Все")
        status = params.get("status", "Все")
        step_like = params.get("step_like", "")
        run_id = params.get("run_id", "")
        limit = params.get("limit", PAGE_SIZE)

        where = []
        sql_params: Dict[str, Any] = {"limit": limit, "mins": minutes}

        # окно по времени (PostgreSQL-совместимо)
        where.append("(COALESCE(ts, created_at) >= (NOW() AT TIME ZONE 'UTC') - make_interval(mins => :mins))")

        if level and level != "Все":
            where.append("(COALESCE(log_level, details->>'level') = :level)")
            sql_params["level"] = level

        if system and system != "Все":
            where.append("(COALESCE(external_system, 'INTERNAL') = :system)")
            sql_params["system"] = system

        if status and status != "Все":
            where.append("(COALESCE(status, 'INFO') = :status)")
            sql_params["status"] = status

        if step_like:
            where.append("(COALESCE(step, '') ILIKE :step)")
            sql_params["step"] = f"%{step_like}%"

        if run_id:
            where.append("(COALESCE(run_id, '') = :run_id)")
            sql_params["run_id"] = run_id

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

        df = pd.read_sql(sql, engine, params=sql_params)

        # Отображаем время в Москве
        if not df.empty and "created_at" in df.columns:
            try:
                df["created_at"] = pd.to_datetime(df["created_at"]).dt.tz_localize(
                    "UTC"
                ).dt.tz_convert("Europe/Moscow")
            except Exception:
                pass
        return df
    except ProgrammingError as e:
        if "relation \"integration_logs\" does not exist" in str(e) or "UndefinedTable" in str(e):
            return "TABLE_NOT_EXISTS"
        return f"ERROR: {e}"
    except Exception as e:
        return f"ERROR: {e}"


@st.cache_data(ttl=POLL_SECONDS)
def load_logs(minutes: int = 60, level: str = "Все", system: str = "Все",
              status: str = "Все", step_like: str = "", run_id: str = "", limit: int = None):
    """Загружает логи из базы данных с фильтрами."""
    if limit is None:
        limit = PAGE_SIZE

    query_params = {
        "mins": minutes,
        "level": level,
        "system": system,
        "status": status,
        "step_like": step_like,
        "run_id": run_id,
        "limit": limit
    }

    return fetch_logs_safe(query_params)


# --- Интерфейс ---
st.set_page_config(page_title="Панель Администратора - Integration Hub", layout="wide")

# Заголовок с информацией о подключениях
st.title("🔧 Панель Администратора")
st.caption(f"DB: {DB_URL.split('@')[1] if '@' in DB_URL else 'N/A'} | App: {APP_BASE}")

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
logs_result = load_logs(
    minutes=minutes,
    level=level_filter,
    system=system_filter,
    status=status_filter,
    step_like=step_filter,
    run_id=run_id_filter
)

if isinstance(logs_result, str):
    # строковые статусы/ошибки
    if logs_result == "TABLE_NOT_EXISTS":
        st.warning("Таблица логов `integration_logs` отсутствует. Создать?")
        if st.button("🔧 Создать таблицу логов сейчас", use_container_width=True):
            create_logs_table()
    elif logs_result.startswith("ERROR:"):
        st.error(f"Ошибка при получении логов: {logs_result[6:]}")
    else:
        st.error(f"Неожиданный результат: {logs_result}")

elif isinstance(logs_result, pd.DataFrame):
    # нормальный рендер
    if logs_result.empty:
        st.info("За выбранный период записей нет.")
    else:
        st.dataframe(logs_result, use_container_width=True)
        st.caption(f"Показано {len(logs_result)} записей за последние {minutes} минут")
else:
    # попробуем привести иные структуры к DataFrame, чтобы не падать
    try:
        df = pd.DataFrame(logs_result)
        if df.empty:
            st.info("За выбранный период записей нет.")
        else:
            st.dataframe(df, use_container_width=True)
            st.caption(f"Показано {len(df)} записей за последние {minutes} минут")
    except Exception as e:
        st.error(f"Неожиданный тип данных журнала: {type(logs_result)} — {e}")

