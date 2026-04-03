"""
Tests for forum API auth in services/alpha/src/health.py.

We intentionally allow the web dashboard to read forum state from whitelisted
origins (CORS allowlist) while blocking anonymous curl-style access unless a
control token is provided.
"""

import os
import sys

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

# Add sapphire_core to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib", "core", "src", "sapphire_core"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lib", "core", "src"))

import health


async def _topics_handler(_payload):
    return {"topics": [{"id": "t1"}]}


async def _topic_detail_handler(payload):
    return {"topic": {"id": payload.get("topic_id", "")}}


def _make_app(cors_origins: str = "https://sapphirealpha.xyz", control_token: str = "") -> web.Application:
    app = web.Application(middlewares=[health.cors_middleware])
    app["cors_allowlist"] = {o.strip() for o in cors_origins.split(",") if o.strip()}
    app["control_api_token"] = control_token
    app["forum_topics_handler"] = _topics_handler
    app["forum_topic_detail_handler"] = _topic_detail_handler
    app.router.add_get("/api/v2/forum/topics", health.forum_topics)
    app.router.add_get("/api/v2/forum/topics/{topic_id}", health.forum_topic_detail)
    return app


@pytest.mark.asyncio
async def test_forum_topics_forbidden_without_origin_or_token():
    app = _make_app(cors_origins="https://sapphirealpha.xyz")
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/v2/forum/topics")
        assert resp.status == 403


@pytest.mark.asyncio
async def test_forum_topics_allowed_with_dashboard_origin():
    app = _make_app(cors_origins="https://sapphirealpha.xyz")
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/v2/forum/topics", headers={"Origin": "https://sapphirealpha.xyz"})
        assert resp.status == 200


@pytest.mark.asyncio
async def test_forum_topics_allowed_with_control_token():
    app = _make_app(cors_origins="https://sapphirealpha.xyz", control_token="tok")
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/v2/forum/topics", headers={"X-Sapphire-Control-Token": "tok"})
        assert resp.status == 200


@pytest.mark.asyncio
async def test_forum_topic_detail_forbidden_without_origin_or_token():
    app = _make_app(cors_origins="https://sapphirealpha.xyz")
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/v2/forum/topics/t1")
        assert resp.status == 403


@pytest.mark.asyncio
async def test_forum_topic_detail_allowed_with_dashboard_origin():
    app = _make_app(cors_origins="https://sapphirealpha.xyz")
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v2/forum/topics/t1", headers={"Origin": "https://sapphirealpha.xyz"}
        )
        assert resp.status == 200


@pytest.mark.asyncio
async def test_forum_topic_detail_allowed_with_control_token():
    app = _make_app(cors_origins="https://sapphirealpha.xyz", control_token="tok")
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/v2/forum/topics/t1", headers={"Authorization": "Bearer tok"})
        assert resp.status == 200

