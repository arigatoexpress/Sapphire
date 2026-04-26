"""Mirror Alpha control-plane kill-switch toggles into the core switch.

Alpha owns the Telegram command UX and already sends user-facing messages. This
bridge records the same manual halt/resume in ``lib.core.kill_switch`` so the
shared audit log and event bus see one canonical state transition too.
"""

from __future__ import annotations

from typing import Protocol


class _ManualKillSwitch(Protocol):
    def force_activate(self, reason: str, *, notify: bool = True) -> bool: ...

    def force_deactivate(self, reason: str, *, notify: bool = True) -> bool: ...


def mirror_alpha_kill_switch(
    active: bool,
    reason: str,
    *,
    switch: _ManualKillSwitch | None = None,
    notify: bool = False,
    source: str = "alpha_control",
) -> bool:
    """Record Alpha's manual kill/resume transition in the core kill switch.

    Returns True only when the core switch recorded a new state transition.
    ``notify`` defaults to False because Alpha sends its own Telegram response.
    """
    target = switch
    if target is None:
        from lib.core.kill_switch import get_kill_switch

        target = get_kill_switch()

    clean_reason = reason.strip() or ("manual kill switch" if active else "manual resume")
    bridged_reason = f"{source}: {clean_reason}"
    if active:
        return target.force_activate(bridged_reason, notify=notify)
    return target.force_deactivate(bridged_reason, notify=notify)
