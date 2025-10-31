"""Minimal Panel dashboard for portfolio telemetry."""

from __future__ import annotations

import os

import hvplot.pandas  # type: ignore
import pandas as pd
import panel as pn

pn.extension("tabulator")

STREAM_API = os.getenv("TRADER_STREAM_API", "http://localhost:8000/streams/positions?limit=200")


def fetch_positions() -> pd.DataFrame:
    try:
        data = pn.io.http.RequestsClient().get(STREAM_API, timeout=5).json()
    except Exception:  # pragma: no cover - network guard
        return pd.DataFrame()
    entries = data.get("entries", [])
    df = pd.DataFrame(entries)
    if not df.empty and "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.sort_values("timestamp")
    return df


positions_table = pn.widgets.Tabulator(pd.DataFrame(), sizing_mode="stretch_both")
balance_plot_pane = pn.pane.HoloViews(sizing_mode="stretch_both")
exposure_plot_pane = pn.pane.HoloViews(sizing_mode="stretch_both")


def refresh() -> None:
    df = fetch_positions()
    if df.empty:
        return
    positions_table.value = df.tail(200)
    balance_plot_pane.object = df.hvplot.line(x="timestamp", y="balance", title="Portfolio Balance")
    exposure_plot_pane.object = df.hvplot.line(
        x="timestamp",
        y="total_exposure",
        color="orange",
        title="Total Exposure",
    )


pn.state.add_periodic_callback(refresh, period=5_000)

layout = pn.Column(
    "## Portfolio Telemetry",
    pn.Row(balance_plot_pane, exposure_plot_pane),
    positions_table,
)

refresh()
layout.servable()

