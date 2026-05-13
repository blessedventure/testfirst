"""
Shared filter logic for channel and user signal delivery.
Supports multi-select strategy, confidence, volume, score, and session filters.
"""
from datetime import datetime
from config import SESSIONS


def passes_strategy_filter(signal_type: str, has_pattern: bool, strategy_list: list) -> bool:
    if "ALL" in strategy_list:
        return True
    for s in strategy_list:
        if s == "TREND" and signal_type == "TREND" and not has_pattern:
            return True
        if s == "RANGE" and signal_type == "RANGE":
            return True
        if s == "PATTERN" and has_pattern:
            return True
    return False


def passes_confidence_filter(confidence: str, confidence_list: list) -> bool:
    if "ALL" in confidence_list:
        return True
    return confidence in confidence_list


def passes_volume_filter(volume_ratio: float, volume_filter: str) -> bool:
    """
    volume_filter values:
      ANY       — any volume passes
      NORMAL    — >= 1.0x
      STRONG    — >= 1.5x
    """
    if volume_filter == "ANY":
        return True
    if volume_filter == "NORMAL":
        return volume_ratio >= 1.0
    if volume_filter == "STRONG":
        return volume_ratio >= 1.5
    return True


def passes_score_filter(score: float, min_score: float) -> bool:
    return score >= min_score


def passes_session_filter(sessions: list) -> bool:
    if "ALL" in sessions:
        return True
    hour = datetime.utcnow().hour
    for sess in sessions:
        if sess in SESSIONS:
            start, end = SESSIONS[sess]
            if start <= hour < end:
                return True
    return False


def signal_passes_for_user(signal, user: dict) -> bool:
    has_pattern = signal.condition.pattern is not None
    if not passes_strategy_filter(
        signal.signal_type, has_pattern,
        user.get("strategy_filter", ["ALL"])
    ):
        return False
    if not passes_confidence_filter(
        signal.confidence,
        user.get("confidence_filter", ["ALL"])
    ):
        return False
    if not passes_volume_filter(
        signal.condition.volume_ratio,
        user.get("volume_filter", "ANY")
    ):
        return False
    if not passes_score_filter(signal.condition.final_score, user["min_score"]):
        return False
    if not passes_session_filter(user["sessions"]):
        return False
    return True


def signal_passes_for_channel(signal, settings: dict) -> bool:
    if not settings.get("is_active", True):
        return False
    has_pattern = signal.condition.pattern is not None
    if not passes_strategy_filter(
        signal.signal_type, has_pattern,
        settings.get("strategy_filter", ["ALL"])
    ):
        return False
    if not passes_confidence_filter(
        signal.confidence,
        settings.get("confidence_filter", ["ALL"])
    ):
        return False
    if not passes_volume_filter(
        signal.condition.volume_ratio,
        settings.get("volume_filter", "ANY")
    ):
        return False
    if not passes_score_filter(signal.condition.final_score, settings["min_score"]):
        return False
    if not passes_session_filter(settings["sessions"]):
        return False
    return True
