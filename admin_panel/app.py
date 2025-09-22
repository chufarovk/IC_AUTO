import asyncio
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st
import requests

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

try:
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine  # optional
except Exception:  # pragma: no cover
    create_async_engine = None
    AsyncEngine = None  # type: ignore

# --------------------
# Settings
# --------------------
DB_URL = os.getenv("ADMIN_DB_URL", "postgresql+psycopg2://user:password@db:5432/bisnesmedia")
APP_URL = os.getenv("ADMIN_APP_URL", "http://app:8000")
POLL_SECONDS = int(os.getenv("ADMIN_POLL_SECONDS", "5"))
PAGE_SIZE = int(os.getenv("ADMIN_PAGE_SIZE", "500"))
TRIGGER_TOKEN = os.getenv("ADMIN_TRIGGER_TOKEN", "")

SHOW_RAW_JSON = True

def _coerce_json(obj: Any, max_len: int = 1500) -> str:
    try:
        s = json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        try:
            s = str(obj)
        except Exception:
            s = "<unserializable>"
    if len(s) > max_len:
        return s[:max_len] + f"... (+{len(s)-max_len} chars)"
    return s

@dataclass
class DbClient:
    db_url: str
    sync_engine: Optional[Engine] = None
    async_engine: Optional["AsyncEngine"] = None
    is_async: bool = False

    def __post_init__(self):
        self.is_async = self.db_url.startswith("postgresql+asyncpg") or self.db_url.startswith("postgresql+aiopg")
        if self.is_async and create_async_engine is not None:
            self.async_engine = create_async_engine(self.db_url, pool_pre_ping=True, future=True)
        else:
            self.sync_engine = create_engine(self.db_url, pool_pre_ping=True, future=True)

    def fetch_logs(
        self,
        level: Optional[str],
        system: Optional[str],
        status: Optional[str],
        step_like: Optional[str],
        run_id: Optional[str],
        minutes: int,
        limit: int,
    ) -> pd.DataFrame:
        where = []
        params: Dict[str, Any] = {"limit": limit, "mins": minutes}

        # единое поле времени
        where.append("(COALESCE(ts, created_at) >= NOW() AT TIME ZONE 'UTC' - INTERVAL :mins MINUTE)")

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

        if self.is_async and self.async_engine is not None:
            return asyncio.get_event_loop().run_until_complete(self._fetch_async(sql, params))
        else:
            assert self.sync_engine is not None
            with self.sync_engine.connect() as conn:
                rs = conn.execute(sql, params)
                rows = rs.mappings().all()
                return pd.DataFrame(rows)

    async def _fetch_async(self, sql, params) -> pd.DataFrame:
        assert self.async_engine is not None
        async with self.async_engine.connect() as conn:
            rs = await conn.execute(sql, params)
            rows = rs.mappings().all()
            return pd.DataFrame(rows)

# --------------------
# UI
# --------------------
st.set_page_config(page_title="Журнал Операций", layout="wide")
st.title("Журнал Операций")

with st.sidebar:
    st.header("Фильтры")
    minutes = st.number_input("Период (минуты)", min_value=5, max_value=24*60, value=60, step=5)
    level = st.selectbox("Уровень", ["Все", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], index=2)
    system = st.selectbox("Система", ["Все", "INTERNAL", "ONEC", "MOYSKLAD"])
    status = st.selectbox("Статус/Level", ["Все", "START", "END", "SUCCESS", "INFO", "WARN", "ERROR"])
    step_like = st.text_input("Шаг (contains)", "")
    run_id = st.text_input("run_id", "")
    warehouse_id = st.text_input("warehouse_id для оценки дефицита", "")
    autorefresh = st.checkbox("Авто-обновление", value=True)
    poll = st.slider("Интервал авто-обновления (сек.)", 2, 30, POLL_SECONDS)
    page_size = st.selectbox("Размер выборки", [100, 200, 500, 1000, 2000], index=[100,200,500,1000,2000].index(PAGE_SIZE))

col_left, col_mid, col_right = st.columns([1,1,2], gap="small")
with col_left:
    refresh = st.button("Обновить логи", type="primary")
with col_mid:
    trigger = st.button("Запустить оценку дефицита", use_container_width=False)

st.caption(f"DB: {DB_URL.split('@')[-1]} | App: {APP_URL}")

# Кнопка триггера
if trigger:
    try:
        url = APP_URL.rstrip("/") + "/api/v1/trigger/internal-replenishment"
        headers = {"Content-Type": "application/json"}
        if TRIGGER_TOKEN:
            headers["X-Admin-Token"] = TRIGGER_TOKEN
        payload = {}
        # если warehouse_id задан — передадим (зависит от вашего роутера, можно убрать)
        if warehouse_id.strip():
            payload["warehouse_id"] = warehouse_id.strip()
        resp = requests.post(url, headers=headers, json=payload or None, timeout=30)
        st.info(f"POST {url} -> {resp.status_code}")
        try:
            st.json(resp.json())
        except Exception:
            st.code(resp.text or "<empty>")
    except Exception as e:
        st.error(f"Ошибка вызова триггера: {e}")

placeholder = st.empty()
client = DbClient(DB_URL)

def render():
    try:
        df = client.fetch_logs(
            level=None if level == "Все" else level,
            system=None if system == "Все" else system,
            status=None if status == "Все" else status,
            step_like=step_like or None,
            run_id=run_id or None,
            minutes=int(minutes),
            limit=int(page_size),
        )
        if df.empty:
            st.info("Нет записей за выбранный период/фильтры.")
            return

        # Превью JSON полей
        def preview_json(col: str) -> List[str]:
            vals = []
            for v in df[col].tolist():
                if v is None:
                    vals.append(None)
                    continue
                try:
                    if isinstance(v, str) and v and (v.startswith("{") or v.startswith("[")):
                        vals.append(_coerce_json(json.loads(v)))
                    else:
                        vals.append(_coerce_json(v))
                except Exception:
                    vals.append(str(v)[:500])
            return vals

        if "details" in df.columns:
            df["details_preview"] = preview_json("details")
        if "payload" in df.columns:
            df["payload_preview"] = preview_json("payload")

        base_cols = ["created_at","process_name","log_level","message","run_id","request_id","job_id","step","status","external_system","elapsed_ms","retry_count","payload_hash"]
        preview_cols = [c for c in ["details_preview","payload_preview"] if c in df.columns]
        show_cols = [c for c in base_cols if c in df.columns] + preview_cols

        st.dataframe(df[show_cols], use_container_width=True, height=600)

        # Экспорт
        c1, c2 = st.columns(2)
        with c1:
            st.download_button("Скачать CSV", df.to_csv(index=False).encode("utf-8"), file_name="integration_logs.csv", mime="text/csv")
        with c2:
            ndjson = "\n".join(_coerce_json(row) for row in df.to_dict(orient="records"))
            st.download_button("Скачать NDJSON", ndjson.encode("utf-8"), file_name="integration_logs.ndjson", mime="application/x-ndjson")

        # Детали строки
        st.markdown("### Детали")
        idx = st.number_input("Индекс строки", min_value=0, max_value=len(df)-1, value=0, step=1)
        row = df.iloc[int(idx)].to_dict()
        st.json(row)
        if SHOW_RAW_JSON:
            with st.expander("details (raw JSON)"):
                st.code(_coerce_json(row.get("details")), language="json")
            with st.expander("payload (raw JSON)"):
                st.code(_coerce_json(row.get("payload")), language="json")

    except SQLAlchemyError as e:
        st.error(f"Ошибка БД: {e}")
    except Exception as e:
        st.error(f"Ошибка рендера: {e}")

# Первый рендер/ручное обновление
render()
if refresh:
    placeholder.empty()
    with placeholder.container():
        render()

# Авто-обновление
if st.session_state.get("_autorefresh", True) and st.checkbox("", value=False, key="_dummy", help="placeholder"):  # no-op
    pass

if True:  # простой цикл автотаила
    if st.session_state.get("_auto_enabled") is None:
        st.session_state["_auto_enabled"] = autorefresh
    elif st.session_state["_auto_enabled"] != autorefresh:
        st.session_state["_auto_enabled"] = autorefresh

    while st.session_state["_auto_enabled"]:
        time.sleep(int(POLL_SECONDS if not 'poll' in globals() else poll))
        placeholder.empty()
        with placeholder.container():
            render()
