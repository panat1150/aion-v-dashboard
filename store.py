from datetime import datetime, timezone
import streamlit as st
from supabase import create_client

_client = None


def _get():
    global _client
    if _client is None:
        _client = create_client(
            st.secrets["supabase"]["url"],
            st.secrets["supabase"]["key"],
        )
    return _client


def get_records(key: str) -> list:
    r = _get().table("data_files").select("content").eq("key", key).execute()
    return r.data[0]["content"] if r.data else []


def save_records(key: str, records: list):
    _get().table("data_files").upsert({
        "key": key,
        "content": records,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
