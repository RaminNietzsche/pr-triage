"""Tracker plugins (Redmine, GitHub Issues, Jira stub, none)."""

from .factory import get_tracker_adapter

__all__ = ["get_tracker_adapter"]
