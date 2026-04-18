"""Live platform publishers for the content engine.

Unlike ``lib.content.publisher`` (which writes drafts to disk for human
review), this package POSTS those drafts to external platforms — LinkedIn,
Substack, X — via their HTTP APIs.

Design notes
------------
* Each client is a thin wrapper around the platform's documented API.
* All credentials come from env vars; nothing is read from disk or code.
* ``dry_run=True`` is the default everywhere: the client validates the
  payload and returns a fake response without hitting the network. The
  LaunchAgent flips ``dry_run=False`` via ``SAPPHIRE_PUBLISH_LIVE=1``.
* Failures never raise — they return a ``PublishResult`` with
  ``ok=False`` so the orchestrator can log the failure and move on.
* Every publish attempt (success or failure) emits a
  ``content.published`` event to the bus and optionally a Telegram ping.
"""

from __future__ import annotations

from .base import PublisherClient, PublishResult, load_client
from .linkedin import LinkedInClient
from .substack import SubstackClient
from .typefully import TypefullyClient
from .x import XClient

__all__ = [
    "PublishResult",
    "PublisherClient",
    "LinkedInClient",
    "SubstackClient",
    "XClient",
    "TypefullyClient",
    "load_client",
]
