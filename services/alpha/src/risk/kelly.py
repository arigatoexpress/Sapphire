from __future__ import annotations


def kelly_fraction(win_prob: float, win_loss_ratio: float) -> float:
    if win_prob <= 0 or win_prob >= 1 or win_loss_ratio <= 0:
        return 0.0
    f = win_prob - (1 - win_prob) / win_loss_ratio
    return max(0.0, f)


def fractional_kelly(win_prob: float, win_loss_ratio: float, fraction: float = 0.5) -> float:
    return kelly_fraction(win_prob, win_loss_ratio) * max(0.0, min(fraction, 1.0))
