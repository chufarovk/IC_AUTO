import os
import socket
from typing import Dict, Any

import httpx
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError
from dotenv import load_dotenv

# Загрузка переменных окружения из .env при локальном запуске
load_dotenv()

# --- Конфигурация ---
def resolve_app_base_url() -> str:
    """Определяем базовый URL для обращения к основному приложению в разных средах."""
    url = os.getenv("ADMIN_APP_URL", "").strip()
    if url:
        return url

    try:
        socket.gethostbyname("app")
        return "http://app"
    except Exception:
        pass

    return "http://localhost:8000"

# --- Настройки ---
APP_BASE = resolve_app_base_url()
DB_URL = os.getenv("ADMIN_DB_URL")
POLL_SECONDS = int(os.getenv("ADMIN_POLL_SECONDS", "5"))
PAGE_SIZE = int(os.getenv("ADMIN_PAGE_SIZE", "500"))

if not DB_URL:
    DB_USER = os.getenv("POSTGRES_USER")
    DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
    DB_SERVER = "db"
    DB_PORT = os.getenv("POSTGRES_PORT", "5432")
    DB_NAME = os.getenv("POSTGRES_DB")
    DB_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_SERVER}:{DB_PORT}/{DB_NAME}"

engine = create_engine(DB_URL)


# --- API helpers ---
def trigger_replenishment(warehouse_id: str = ""):
    """Синхронно вызывает POST-эндпоинт для запуска пополнения."""
    try:
        url = APP_BASE.rstrip("/") + "/api/v1/trigger/internal-replenishment"
        headers = {"Content-Type": "application/json"}
        payload = {"warehouse_id": warehouse_id.strip()} if warehouse_id.strip() else None

        with httpx.Client() as client:
            response = client.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            st.success(f"Запрос обработан успешно! Код состояния: {response.status_code}")
            if response.text:
                try:
                    result = response.json()
                    st.json(result)
                except Exception:
                    st.text(response.text)
    except httpx.HTTPStatusError as e:
        st.error(f"Ошибка при вызове сервиса пополнения: {e.response.status_code} - {e.response.text}")
    except Exception as e:
        st.error(f"Непредвиденная ошибка: {e}")


def create_logs_table():
    """Пробует создать таблицу integration_logs через API приложения."""
    try:
        url = APP_BASE.rstrip("/") + "/admin/init_logs_table"
        headers = {"Content-Type": "application/json"}

        with httpx.Client() as client:
            response = client.post(url, headers=headers, timeout=30)
            response.raise_for_status()
            st.success("Таблица создана/актуализирована успешно!")
            st.rerun()
    except httpx.HTTPStatusError as e:
        st.error(f"Ошибка при создании таблицы: {e.response.status_code} - {e.response.text}")
    except Exception as e:
        st.error(f"Непредвиденная ошибка при создании таблицы: {e}")


def fetch_logs_safe(params: dict):
    """
    Безопасное получение данных из таблицы логов.
    Возвращает:
      * pd.DataFrame при успешной загрузке
      * строку "TABLE_NOT_EXISTS", если таблица отсутствует
      * строку вида "ERROR: ..." для прочих ошибок
    """
    query = text(
        """
        SELECT
            ts,
            run_id,
            request_id,
            job_id,
            job_name,
            step,
            status,
            external_system,
            elapsed_ms,
            retry_count,
            payload_hash,
            details,
            payload,
            process_name,
            log_level,
            message
        FROM integration_logs
        WHERE ts >= NOW() - INTERVAL :minutes || ' minutes'
          AND (:level = 'ВСЁ' OR log_level = :level)
          AND (:system = 'ВСЁ' OR external_system = :system)
          AND (:status = 'ВСЁ' OR status = :status)
          AND (:step IS NULL OR step ILIKE '%' || :step || '%')
          AND (:run_id IS NULL OR run_id::text = :run_id)
        ORDER BY ts DESC
        LIMIT :limit
        """
    )

    try:
        with engine.connect() as conn:
            df = pd.read_sql_query(query, conn, params=params)
            return df
    except ProgrammingError as exc:
        if "relation \"integration_logs\" does not exist" in str(exc):
            return "TABLE_NOT_EXISTS"
        return f"ERROR: {exc}"
    except Exception as exc:
        return f"ERROR: {exc}"


@st.cache_data(ttl=POLL_SECONDS)
def load_logs(*, minutes: int, level: str, system: str, status: str, step_like: str | None, run_id: str | None):
    params = {
        "minutes": minutes,
        "level": level,
        "system": system,
        "status": status,
        "step": step_like or None,
        "run_id": run_id or None,
        "limit": PAGE_SIZE,
    }
    return fetch_logs_safe(params)


# --- UI ---
st.title("Центр управления интеграциями")
st.caption(f"DB: {DB_URL.split('@')[1] if '@' in DB_URL else 'N/A'} | App: {APP_BASE}")

st.header("Фоновые операции и ручные действия")
col1, col2 = st.columns(2)

with col1:
    warehouse_id = st.text_input("ID склада (опционально):", placeholder="Например: Юрловский")
    if st.button("Запустить внутреннее пополнение", use_container_width=True):
        trigger_replenishment(warehouse_id)

with col2:
    st.button("Сформировать внешние заказы (в разработке)", disabled=True, use_container_width=True)
    st.caption("Функция появится позже")

st.divider()

st.header("Журнал интеграционных событий")

col1, col2, col3, col4 = st.columns(4)
with col1:
    minutes = st.number_input("Период (минуты):", min_value=1, max_value=1440, value=60)
with col2:
    level_filter = st.selectbox("Уровень логов:", ["ВСЁ", "DEBUG", "INFO", "WARN", "ERROR"])
with col3:
    system_filter = st.selectbox("Система:", ["ВСЁ", "INTERNAL", "ONEC", "MOYSKLAD"])
with col4:
    status_filter = st.selectbox("Статус шага:", ["ВСЁ", "INFO", "SUCCESS", "ERROR", "STARTED", "COMPLETED"])

col5, col6 = st.columns(2)
with col5:
    step_filter = st.text_input("Контекст шага:", placeholder="Например: replenishment")
with col6:
    run_id_filter = st.text_input("Run ID:", placeholder="UUID процесса")

if st.button("Обновить результаты"):
    st.cache_data.clear()

logs_result = load_logs(
    minutes=minutes,
    level=level_filter,
    system=system_filter,
    status=status_filter,
    step_like=step_filter,
    run_id=run_id_filter,
)

if isinstance(logs_result, str) and logs_result == "TABLE_NOT_EXISTS":
    st.warning("Таблица `integration_logs` отсутствует. Примените миграции.")
    if st.button("Создать таблицу логов", use_container_width=True):
        create_logs_table()
elif isinstance(logs_result, str) and logs_result.startswith("ERROR:"):
    st.error(f"Ошибка при выборке логов: {logs_result[6:]}")
elif isinstance(logs_result, str):
    st.error(f"Неподдерживаемый ответ: {logs_result}")
elif logs_result is None:
    st.info("Нет данных за выбранный период.")
elif isinstance(logs_result, pd.DataFrame) and logs_result.empty:
    st.info("Нет записей за выбранный период.")
elif isinstance(logs_result, pd.DataFrame):
    st.dataframe(logs_result, use_container_width=True)
    st.caption(f"Показано {len(logs_result)} записей за последние {minutes} минут.")
else:
    try:
        df = pd.DataFrame(logs_result)
        if df.empty:
            st.info("Нет записей за выбранный период.")
        else:
            st.dataframe(df, use_container_width=True)
            st.caption(f"Показано {len(df)} записей за последние {minutes} минут.")
    except Exception as exc:
        st.error(f"Не удалось отобразить результат. Тип: {type(logs_result)}. Ошибка: {exc}")
