from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List

import pandas as pd
import panel as pn
from panel import indicators
from redis.asyncio import Redis

pn.extension("tabulator")


class RedisStreamReader:
    def __init__(self, redis_url: str, stream: str) -> None:
        self._redis = Redis.from_url(redis_url, decode_responses=False)
        self._stream = stream
        self._last_id = "$"

    async def poll(self) -> List[Dict[str, Any]]:
        response = await self._redis.xread({self._stream: self._last_id}, timeout=1000, count=200)
        events: List[Dict[str, Any]] = []
        for stream_name, entries in response or []:
            for entry_id, payload in entries:
                self._last_id = entry_id
                data = json.loads(payload.get(b"payload", b"{}"))
                events.append(data)
        return events


class Dashboard:
    def __init__(self, redis_url: str) -> None:
        self._decisions = RedisStreamReader(redis_url, "trader:decisions")
        self._positions = RedisStreamReader(redis_url, "trader:positions")
        self._reasoning = RedisStreamReader(redis_url, "trader:reasoning")

        empty = pd.DataFrame()
        self.decision_table = pn.widgets.Tabulator(empty, height=280)
        self.position_table = pn.widgets.Tabulator(empty, height=280)
        self.reasoning_feed = pn.pane.Markdown("_Waiting for reasoning events..._", sizing_mode="stretch_width")
        self.balance_indicator = indicators.Number(name="Balance", value=0.0, format="${value:,.2f}")
        self.exposure_indicator = indicators.Number(name="Total Exposure", value=0.0, format="${value:,.2f}")

    async def run(self) -> None:
        while True:
            decisions, positions, reasoning = await asyncio.gather(
                self._decisions.poll(), self._positions.poll(), self._reasoning.poll()
            )

            if decisions:
                df = pd.DataFrame(decisions).tail(200)
                df["timestamp"] = pd.to_datetime(df.get("timestamp") or df.get("time", []))
                self.decision_table.value = df
            if positions:
                df = pd.DataFrame(positions).tail(200)
                df["timestamp"] = pd.to_datetime(df.get("timestamp", pd.Timestamp.utcnow()))
                self.position_table.value = df
                latest = df.iloc[-1]
                try:
                    self.balance_indicator.value = float(latest.get("balance", 0))
                    self.exposure_indicator.value = float(latest.get("total_exposure", 0))
                except (TypeError, ValueError):
                    pass
            if reasoning:
                lines = []
                for item in reasoning[-10:]:
                    symbol = item.get("symbol") or item.get("bot_id", "unknown")
                    message = item.get("message", "")
                    context = item.get("context")
                    if isinstance(context, str):
                        try:
                            context_obj = json.loads(context)
                            context = context_obj
                        except json.JSONDecodeError:
                            pass
                    lines.append(f"- **{symbol}** — {message}\n    ```json\n    {json.dumps(context, indent=2) if isinstance(context, dict) else context}\n    ```")
                self.reasoning_feed.object = "\n".join(lines)

            await asyncio.sleep(1)

    def layout(self) -> pn.template.MaterialTemplate:
        template = pn.template.MaterialTemplate(title="Trader Telemetry")
        template.main.append(
            pn.Row(
                self.balance_indicator,
                self.exposure_indicator,
            )
        )
        template.main.append(pn.Column("### Decisions", self.decision_table))
        template.main.append(pn.Column("### Portfolio", self.position_table))
        template.main.append(pn.Column("### Reasoning", self.reasoning_feed))
        return template


def main() -> None:
    redis_url = pn.state.session_args.get("redis", [b"redis://localhost:6379/0"])[0].decode()
    dashboard = Dashboard(redis_url)

    loop = asyncio.get_event_loop()
    loop.create_task(dashboard.run())
    dashboard.layout().servable()


if __name__ == "__main__":
    main()

