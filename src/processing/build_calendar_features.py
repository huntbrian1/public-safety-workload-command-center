from __future__ import annotations

from datetime import date, timedelta

import pandas as pd


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d + timedelta(days=7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        d = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        d = date(year, month + 1, 1) - timedelta(days=1)
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d


def _observed(d: date) -> date:
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def us_federal_holidays(years: list[int] | range) -> set[date]:
    holidays: set[date] = set()
    for year in years:
        fixed = [
            date(year, 1, 1),
            date(year, 6, 19),
            date(year, 7, 4),
            date(year, 11, 11),
            date(year, 12, 25),
        ]
        holidays.update(fixed)
        holidays.update(_observed(d) for d in fixed)
        holidays.add(_nth_weekday(year, 1, 0, 3))   # MLK Day
        holidays.add(_nth_weekday(year, 2, 0, 3))   # Presidents Day
        holidays.add(_last_weekday(year, 5, 0))     # Memorial Day
        holidays.add(_nth_weekday(year, 9, 0, 1))   # Labor Day
        holidays.add(_nth_weekday(year, 10, 0, 2))  # Indigenous Peoples/Columbus Day
        holidays.add(_nth_weekday(year, 11, 3, 4))  # Thanksgiving
    return holidays


def season_for_month(month: int) -> str:
    if month in {12, 1, 2}:
        return "Winter"
    if month in {3, 4, 5}:
        return "Spring"
    if month in {6, 7, 8}:
        return "Summer"
    return "Fall"


def add_calendar_features(df: pd.DataFrame, datetime_col: str = "event_datetime") -> pd.DataFrame:
    out = df.copy()
    dt = pd.to_datetime(out[datetime_col], errors="coerce")
    out["event_datetime"] = dt
    out["event_date"] = dt.dt.date
    out["event_hour"] = dt.dt.hour.astype("Int64")
    out["weekday"] = dt.dt.weekday.astype("Int64")
    out["weekday_name"] = dt.dt.day_name()
    out["month"] = dt.dt.month.astype("Int64")
    out["month_name"] = dt.dt.month_name()
    out["quarter"] = dt.dt.quarter.astype("Int64")
    out["year"] = dt.dt.year.astype("Int64")
    out["is_weekend"] = out["weekday"].isin([5, 6])
    years = [int(y) for y in out["year"].dropna().unique()]
    holidays = us_federal_holidays(range(min(years) - 1, max(years) + 2)) if years else set()
    out["is_holiday"] = out["event_date"].isin(holidays)
    out["is_business_hour"] = out["event_hour"].between(8, 17) & ~out["is_weekend"] & ~out["is_holiday"]
    out["is_after_hours"] = ~out["is_business_hour"]
    out["season"] = out["month"].apply(lambda m: season_for_month(int(m)) if pd.notna(m) else pd.NA)
    return out
