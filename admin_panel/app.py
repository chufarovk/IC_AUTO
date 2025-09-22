import os

import httpx
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# --- Настройки ---
API_BASE_URL = "http://app:80"  # Внутри Docker сети обращаемся по имени сервиса
DB_USER = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DB_SERVER = "db"  # Внутри Docker сети
DB_PORT = os.getenv("POSTGRES_PORT")
DB_NAME = os.getenv("POSTGRES_DB")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_SERVER}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL)


# --- Функции ---
def trigger_process(endpoint: str):
    """Отправляет POST-запрос для запуска процесса."""
    try:
        with httpx.Client() as client:
            response = client.post(f"{API_BASE_URL}{endpoint}")
            response.raise_for_status()
            st.success(
                f"Процесс успешно запущен! Ответ сервера: {response.json().get('message')}"
            )
    except httpx.HTTPStatusError as e:
        st.error(
            f"Ошибка при запуске процесса: {e.response.status_code} - {e.response.text}"
        )
    except Exception as e:
        st.error(f"Критическая ошибка: {e}")


@st.cache_data(ttl=60)  # Кэшируем данные на 60 секунд
def load_logs():
    """Загружает логи из базы данных."""
    try:
        query = (
            "SELECT created_at, process_name, log_level, message, payload "
            "FROM integration_logs ORDER BY created_at DESC LIMIT 500"
        )
        df = pd.read_sql(query, engine)
        # Отображаем время в Москве
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
st.set_page_config(page_title="Панель Управления Интеграцией", layout="wide")

st.title("Панель Управления Интеграцией")

# --- Секция Ручного Управления ---
st.header("Ручное Управление")
col1, col2 = st.columns(2)

with col1:
    if st.button("🚀 Запустить внутреннее перемещение (1С)", use_container_width=True):
        trigger_process("/api/v1/trigger/internal-replenishment")

with col2:
    st.button(
        "📦 Запустить внешний заказ (МойСклад)", disabled=True, use_container_width=True
    )
    st.caption("Функционал в разработке")

st.divider()

# --- Секция Журнала Операций ---
st.header("Журнал Операций")

if st.button("🔄 Обновить логи"):
    st.cache_data.clear()

logs_df = load_logs()

if not logs_df.empty:
    # Фильтры
    log_levels = logs_df["log_level"].unique()
    selected_level = st.selectbox(
        "Фильтр по уровню:", options=["Все"] + list(log_levels)
    )

    if selected_level != "Все":
        filtered_df = logs_df[logs_df["log_level"] == selected_level]
    else:
        filtered_df = logs_df

    st.dataframe(filtered_df, use_container_width=True)
else:
    st.warning("Логи отсутствуют или не удалось их загрузить.")

