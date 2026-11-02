"""Load and validate `.pr-triage.yml` / `configs/<profile>.yml`."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from pr_triage.safepath import SafePath, allowed_base, resolve_config_path


@dataclass
class PathRule:
    prefix: str
    component: str


@dataclass
class ComponentConfig:
    label_priority: list[str]
    path_rules: list[PathRule]
    generic_labels: frozenset[str] = frozenset({"documentation", "tests", "build/ops", "common", "pybind"})


@dataclass
class TrackerConfig:
    plugin: str  # redmine | github_issues | jira | none
    base_url: str = ""
    issue_id_regex: str = r"github\.com/.+/issues/(\d+)"
    user_agent: str = "pr-triage (read-only)"
    delay_s: float = 1.0
    cache_max_age_s: int = 24 * 3600
    fix_landed_statuses: frozenset[str] = frozenset()
    not_fixed_statuses: frozenset[str] = frozenset()
    backport_tracker_name: str = "Backport"
    release_branches: frozenset[str] = frozenset()
    branch_title_prefixes: frozenset[str] = frozenset()  # strip from titles in dupes


@dataclass
class GitHubConfig:
    repo: str
    default_base: str = "main"
    clone_dir: str = "data/repo/project"
    release_branches: frozenset[str] = frozenset()


@dataclass
class LabelsConfig:
    needs_rebase: str = "needs-rebase"
    stale: str = "stale"
    pinned: str = "pinned"


@dataclass
class ThresholdsConfig:
    inactive_days: int = 365
    min_cherry_share: float = 0.25
    rename_similarity_percent: int = 50  # git diff -M / --find-renames threshold
    basename_move_fallback: bool = True  # same-basename search on base when git finds no rename


@dataclass
class LimitsConfig:
    max_prs_analyse: int | None = None  # cap for smoke runs on huge backlogs


@dataclass
class DataPaths:
    data_dir: str = "data"
    raw_dir: str = "data/raw"
    prs_cache: str = "data/prs.json"
    tracker_cache: str = "data/tracker"


@dataclass
class ScopeConfig:
    name: str
    component: str = "all"
    path_prefix: str | None = None


@dataclass
class ReportConfig:
    """User-facing report title and tool attribution (from profile YAML)."""

    display_name: str
    tool_name: str


@dataclass
class TriageConfig:
    name: str
    github: GitHubConfig
    components: ComponentConfig
    tracker: TrackerConfig
    labels: LabelsConfig = field(default_factory=LabelsConfig)
    thresholds: ThresholdsConfig = field(default_factory=ThresholdsConfig)
    limits: LimitsConfig = field(default_factory=LimitsConfig)
    paths: DataPaths = field(default_factory=DataPaths)
    scopes: list[ScopeConfig] = field(default_factory=list)
    path_prefix_template: str = "src/{component}/"
    enabled_categories: frozenset[str] | None = None
    limitations_extra: list[str] = field(default_factory=list)
    report: ReportConfig = field(default_factory=lambda: ReportConfig(display_name="Project", tool_name="pr-triage"))

    @property
    def repo_slug(self) -> str:
        return self.github.repo.split("/")[-1]

    def clone_path(self) -> Path:
        return Path(self.github.clone_dir)

    def tracker_grep_fragment(self) -> str:
        """Pattern fragment for git log --grep (tracker URL in commits)."""
        # Derive host/path from issue_id_regex when it looks like a URL tracker
        pat = self.tracker.issue_id_regex
        marker = "/issues/"
        pos = pat.lower().find(marker)
        if pos == -1:
            return "issues/"
        host_part = pat[:pos].replace(r"\.", ".")
        while host_part and host_part[-1] in ".+*?":
            host_part = host_part[:-1]
        host_part = host_part.rstrip("/\\")
        return f"{host_part}{marker}" if host_part else "issues/"


def _path_rules(raw: list[Any]) -> list[PathRule]:
    out: list[PathRule] = []
    for item in raw or []:
        if isinstance(item, dict):
            out.append(PathRule(prefix=str(item["prefix"]), component=str(item["component"])))
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            out.append(PathRule(prefix=str(item[0]), component=str(item[1])))
    return out


def load_config(path: str | Path | None) -> TriageConfig:
    path = resolve_config_path(path or "configs/ceph.yml")
    if not path.is_file():
        raise FileNotFoundError(path)
    data = yaml.safe_load(SafePath(path, allowed_base()).read_text()) or {}
    gh = data.get("github") or {}
    tr = data.get("tracker") or {}
    comp = data.get("components") or {}
    paths = data.get("paths") or {}
    limits = data.get("limits") or {}
    scopes_raw = data.get("scopes") or []

    github = GitHubConfig(
        repo=str(gh.get("repo", "owner/repo")),
        default_base=str(gh.get("default_base", "main")),
        clone_dir=str(gh.get("clone_dir", paths.get("clone_dir", f"data/repo/{path.stem}"))),
        release_branches=frozenset(gh.get("release_branches") or tr.get("release_branches") or ()),
    )
    tracker = TrackerConfig(
        plugin=str(tr.get("plugin", "none")),
        base_url=str(tr.get("base_url", "")),
        issue_id_regex=str(tr.get("issue_id_regex", TrackerConfig.issue_id_regex)),
        user_agent=str(tr.get("user_agent", "pr-triage (read-only)")),
        delay_s=float(tr.get("delay_s", 1.0)),
        cache_max_age_s=int(tr.get("cache_max_age_s", 24 * 3600)),
        fix_landed_statuses=frozenset(tr.get("fix_landed_statuses") or ()),
        not_fixed_statuses=frozenset(tr.get("not_fixed_statuses") or ()),
        backport_tracker_name=str(tr.get("backport_tracker_name", "Backport")),
        release_branches=frozenset(tr.get("release_branches") or github.release_branches),
        branch_title_prefixes=frozenset(tr.get("branch_title_prefixes") or ()),
    )
    components = ComponentConfig(
        label_priority=list(comp.get("label_priority") or ()),
        path_rules=_path_rules(comp.get("path_rules")),
        generic_labels=frozenset(comp.get("generic_labels") or ComponentConfig.generic_labels),
    )
    labels = LabelsConfig(**{k: data.get("labels", {}).get(k, v) for k, v in LabelsConfig().__dict__.items()})
    th = data.get("thresholds") or {}
    bmf = th.get("basename_move_fallback", True)
    thresholds = ThresholdsConfig(
        inactive_days=int(th.get("inactive_days", 365)),
        min_cherry_share=float(th.get("min_cherry_share", 0.25)),
        rename_similarity_percent=int(th.get("rename_similarity_percent", 50)),
        basename_move_fallback=bool(bmf) if bmf is not None else True,
    )
    lim = LimitsConfig(max_prs_analyse=limits.get("max_prs_analyse"))
    data_paths = DataPaths(
        data_dir=str(paths.get("data_dir", "data")),
        raw_dir=str(paths.get("raw_dir", "data/raw")),
        prs_cache=str(paths.get("prs_cache", "data/prs.json")),
        tracker_cache=str(paths.get("tracker_cache", "data/tracker")),
    )
    scopes = [
        ScopeConfig(
            name=str(s.get("name", s.get("component", "all"))),
            component=str(s.get("component", "all")),
            path_prefix=s.get("path_prefix"),
        )
        for s in scopes_raw
    ]
    cats = data.get("enabled_categories")
    profile = str(data.get("name", path.stem))
    rep_raw = data.get("report") or {}
    repo_slug = github.repo.split("/")[-1]
    display_name = str(rep_raw.get("display_name") or repo_slug.replace("-", " ").title())
    tool_name = str(rep_raw.get("tool_name") or ("ceph-pr-triage" if profile == "ceph" else "pr-triage"))
    report = ReportConfig(display_name=display_name, tool_name=tool_name)
    return TriageConfig(
        name=profile,
        github=github,
        components=components,
        tracker=tracker,
        labels=labels,
        thresholds=thresholds,
        limits=lim,
        paths=data_paths,
        scopes=scopes,
        path_prefix_template=str(data.get("path_prefix_template", "src/{component}/")),
        enabled_categories=frozenset(cats) if cats else None,
        limitations_extra=list(data.get("limitations_extra") or ()),
        report=report,
    )
