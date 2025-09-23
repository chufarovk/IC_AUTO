Отлично: триггер теперь бьётся в http://app и отдаёт 202 — это ок. Осталась одна проблема в админке: сравниваешь DataFrame со строкой (logs_df == "TABLE_NOT_EXISTS"), из-за чего Streamlit падает.

Ниже — готовый фикс. Просто замени блок рендера логов (тот, где сейчас стоит if logs_df == "TABLE_NOT_EXISTS":) на этот код и перезапусти контейнер admin_panel.

🔧 Заменить блок рендера логов в admin_panel/app.py
# --- BEGIN FIX: safe logs rendering ---
import pandas as pd
import sqlalchemy as sa

def fetch_logs_safe(params: dict):
    """
    Обёртка получения логов:
    - на успехе: возвращает pd.DataFrame
    - если таблицы нет: строку-сентинел 'TABLE_NOT_EXISTS'
    - на иных ошибках: строка 'ERROR: ...'
    """
    try:
        # твоя текущая реализация выборки:
        # пример — адаптируй под свою функцию/SQL
        engine = sa.create_engine(os.getenv("ADMIN_DB_URL"))
        sql = sa.text("""
            SELECT
              COALESCE(ts, created_at)            AS created_at,
              COALESCE(process_name, step)        AS process_name,
              COALESCE(log_level, status)         AS log_level,
              COALESCE(message, details->>'message') AS message,
              run_id, request_id, job_id, step, status, external_system,
              elapsed_ms, retry_count, payload_hash, details, payload
            FROM integration_logs
            WHERE COALESCE(ts, created_at) >= (NOW() AT TIME ZONE 'UTC') - make_interval(mins => :mins)
            ORDER BY COALESCE(ts, created_at) DESC
            LIMIT :limit
        """)
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn, params={"mins": params.get("mins", 60), "limit": params.get("limit", 500)})
        return df
    except sa.exc.ProgrammingError as e:
        if 'relation "integration_logs" does not exist' in str(e):
            return "TABLE_NOT_EXISTS"
        return f"ERROR: {e}"
    except Exception as e:
        return f"ERROR: {e}"

# где-то выше ты уже собрал параметры фильтров:
query_params = {
    "mins": period_minutes,  # твоя переменная из UI
    "limit": page_size,      # твоя переменная из UI
}

logs_result = fetch_logs_safe(query_params)

if isinstance(logs_result, str):
    # строковые статусы/ошибки
    if logs_result == "TABLE_NOT_EXISTS":
        st.warning("Таблица логов `integration_logs` отсутствует. Создать?")
        if st.button("Создать таблицу логов"):
            try:
                resp = call_app("/admin/init_logs_table", method="POST", timeout=20)
                st.success("Таблица создана. Обновите страницу или повторите запрос.")
            except Exception as e:
                st.error(f"Не удалось создать таблицу: {e}")
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
else:
    # попробуем привести иные структуры к DataFrame, чтобы не падать
    try:
        df = pd.DataFrame(logs_result)
        if df.empty:
            st.info("За выбранный период записей нет.")
        else:
            st.dataframe(df, use_container_width=True)
    except Exception as e:
        st.error(f"Неожиданный тип данных журнала: {type(logs_result)} — {e}")
# --- END FIX ---


Ключевая идея: никогда не сравнивай DataFrame со строкой. Сначала проверяй тип через isinstance, а уже потом обрабатывай.