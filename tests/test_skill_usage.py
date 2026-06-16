"""Tests fuer analysis/skill_usage.py (Skill-Usage-Aggregation)."""
import importlib.util
from pathlib import Path

MOD = Path(__file__).resolve().parents[1] / "analysis" / "skill_usage.py"
_spec = importlib.util.spec_from_file_location("skill_usage", MOD)
su = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(su)


def _ev(skill, project, phase="pre", ts="2026-06-16 10:00:00"):
    return {"tool_name": "Skill", "summary": skill, "project": project,
            "phase": phase, "ts_local": ts}


def test_counts_dedup_post_and_scope_global_vs_local():
    events = [
        _ev("frontend-design", "dco"),
        _ev("frontend-design", "wiki"),
        _ev("tdd", "dco"),
        _ev("tdd", "dco", ts="2026-06-16 11:00:00"),
        _ev("tdd", "dco", phase="post"),          # post darf NICHT mitzaehlen
        {"tool_name": "Bash", "summary": "ls",     # Nicht-Skill ignoriert
         "project": "dco", "phase": "pre"},
    ]
    by = {s["skill"]: s for s in su.skill_usage_stats(events)}

    assert by["tdd"]["count"] == 2                 # post ignoriert
    assert by["tdd"]["scope_hint"] == "lokal:dco"
    assert by["tdd"]["last_used"] == "2026-06-16 11:00:00"
    assert by["frontend-design"]["count"] == 2
    assert by["frontend-design"]["project_count"] == 2
    assert by["frontend-design"]["scope_hint"] == "global"


def test_sorted_by_count_desc():
    events = [_ev("a", "p1")] + [_ev("b", "p1") for _ in range(3)]
    stats = su.skill_usage_stats(events)
    assert [s["skill"] for s in stats] == ["b", "a"]


def test_missing_skill_name_bucketed_unknown():
    stats = su.skill_usage_stats([_ev("", "dco"), _ev("   ", "dco")])
    assert len(stats) == 1
    assert stats[0]["skill"] == "(unbekannt)"
    assert stats[0]["count"] == 2


def test_empty_events_returns_empty():
    assert su.skill_usage_stats([]) == []
