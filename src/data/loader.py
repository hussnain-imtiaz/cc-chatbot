import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path


# excel counts days from this date
EXCEL_EPOCH = datetime(1899, 12, 30)

# simple module-level cache so we don't re-read 3 CSVs on every function call
_loaded = {}


def parse_string_interval(s):
    # handles '01/01/2026 (00:00:00 - 00:59:59)' -> datetime
    # the time range part after the dash is just showing end of hour, we only need start
    if not isinstance(s, str):
        return datetime(2026, 1, 1)  # fallback for the null row
    date_bit = s.split("(")[0].strip()
    time_bit = s.split("(")[1].split("-")[0].strip()
    return datetime.strptime(f"{date_bit} {time_bit}", "%d/%m/%Y %H:%M:%S")


def parse_excel_serial(v):
    try:
        return EXCEL_EPOCH + timedelta(days=float(v))
    except (ValueError, TypeError):
        return datetime(2026, 1, 1)  # fallback for the null row


def _prep(df):
    # stuff every dataframe needs regardless of source
    df["date"] = df["dt"].dt.date
    df["hour"] = df["dt"].dt.hour
    df["weekday"] = df["dt"].dt.day_name()
    # business hours = 8am to 5:59pm
    df["is_biz_hours"] = df["hour"].between(8, 17)
    return df


def load_estate(path):
    df = pd.read_csv(path)
    df = df.dropna(subset=["Interval"]).reset_index(drop=True)
    df["dt"] = df["Interval"].apply(parse_string_interval)
    return _prep(df)


def load_queues(path):
    df = pd.read_csv(path)
    serial_col = df.columns[0]  # always the first column, named something with "Serial"
    df = df.dropna(subset=[serial_col]).reset_index(drop=True)
    df["dt"] = df[serial_col].apply(parse_excel_serial)
    df["queue_name"] = df["Description"].fillna("Unknown")
    return _prep(df)


def load_agents(path):
    df = pd.read_csv(path)
    df = df.dropna(subset=["Interval"]).reset_index(drop=True)
    df["dt"] = df["Interval"].apply(parse_string_interval)
    df["agent_name"] = df["Description"].fillna("Unknown")
    return _prep(df)


def load_all(data_dir="data"):
    if data_dir in _loaded:
        return _loaded[data_dir]

    base = Path(data_dir)
    result = {
        "estate": load_estate(base / "estate.csv"),
        "queues": load_queues(base / "queues.csv"),
        "agents": load_agents(base / "agents.csv"),
    }
    _loaded[data_dir] = result
    return result