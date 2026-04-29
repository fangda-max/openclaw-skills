from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any
import xml.etree.ElementTree as ET

from entropy_audit.config import ProjectConfig
from entropy_audit.lang.base import LanguageAdapter, LanguageScaffold
from entropy_audit.lang.java.runner import analyze_code_entropy, build_code_entropy_export, discover_internal_package_prefixes


DOC_SCAN_DIRS = ("docs", "doc", "readme", "runbooks", "plans", "ops", "operations")
JAVA_TEMPLATE_DIR = Path(__file__).with_name("templates")
JAVA_CONFIG_TEMPLATE_PATH = JAVA_TEMPLATE_DIR / "entropy.config.toml.tmpl"
JAVA_CALIBRATION_TEMPLATE_PATH = JAVA_TEMPLATE_DIR / "entropy.calibration.toml.tmpl"
SKIP_DIR_NAMES = {
    ".git",
    ".idea",
    ".history",
    ".cursor",
    ".claude",
    ".codex-temp",
    ".graphify_python",
    "graphify-out",
    "target",
    "node_modules",
    "build",
    "dist",
    "__pycache__",
}
ARCHITECTURE_KEYWORDS = ("architecture", "arch", "adr", "design", "overview", "quickstart", "guide", "快速入门", "开发说明")
RUNBOOK_KEYWORDS = (
    "runbook",
    "startup",
    "setup",
    "deploy",
    "rollback",
    "operation",
    "ops",
    "job",
    "task",
    "execution",
    "local",
    "发布",
    "回滚",
    "启动",
    "部署",
    "定时任务",
    "运行",
)
PLAN_KEYWORDS = ("plan", "plans", "roadmap", "milestone", "backlog", "exec-plan", "方案", "计划", "治理", "实施")
DOC_HINT_ALIASES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("architecture", "adr", "design", "overview", "quickstart", "guide", "快速入门", "开发说明"), "architecture"),
    (("deploy", "rollback", "release", "部署", "发布", "回滚"), "deploy-or-rollback"),
    (("job", "execution", "schedule", "cron", "task", "定时任务"), "job-execution"),
    (("local", "startup", "setup", "boot", "本地", "启动"), "local-dev-startup"),
)


@dataclass(slots=True)
class BuildDetection:
    tool: str
    build: str
    test: str
    module_paths: list[str]


def _toml_array(values: list[str]) -> str:
    if not values:
        return "[]"
    return "[" + ", ".join(_toml_string(value) for value in values) + "]"


def _toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _toml_key(key: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]+", key):
        return key
    return _toml_string(key)


def _render_array_table(name: str, mapping: dict[str, list[str]]) -> str:
    if not mapping:
        return ""
    lines = [f"[{name}]"]
    for key, values in mapping.items():
        lines.append(f"{_toml_key(key)} = {_toml_array(values)}")
    return "\n".join(lines)


def _render_string_table(name: str, mapping: dict[str, str]) -> str:
    if not mapping:
        return ""
    lines = [f"[{name}]"]
    for key, value in mapping.items():
        lines.append(f"{_toml_key(key)} = {_toml_string(value)}")
    return "\n".join(lines)

def _load_template(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Java init template not found: {path}")
    return path.read_text(encoding="utf-8")


def _render_template(
    template: str,
    replacements: dict[str, str],
    *,
    allow_unresolved: set[str] | None = None,
) -> str:
    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    allowed = {item.strip() for item in (allow_unresolved or set()) if item and item.strip()}
    unresolved = sorted(
        placeholder
        for placeholder in set(re.findall(r"\{\{[A-Z0-9_]+\}\}", rendered))
        if placeholder.strip("{}") not in allowed
    )
    if unresolved:
        raise ValueError(f"Unresolved Java init template placeholders: {', '.join(unresolved)}")
    return rendered


def _existing_paths(project_root: Path, candidates: list[str], fallbacks: list[str]) -> list[str]:
    matches = [candidate for candidate in candidates if (project_root / candidate).exists()]
    return _dedupe(matches) or fallbacks


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _relative_path(project_root: Path, path: Path) -> str:
    return path.relative_to(project_root).as_posix()


def _module_candidates_from_tree(project_root: Path) -> list[str]:
    candidates: list[str] = []
    for child in project_root.iterdir():
        if not child.is_dir() or child.name in SKIP_DIR_NAMES or child.name.startswith("."):
            continue
        if (child / "pom.xml").exists() or (child / "build.gradle").exists() or (child / "build.gradle.kts").exists():
            candidates.append(_relative_path(project_root, child))
            continue
        if (child / "src" / "main" / "java").exists() or (child / "src" / "test" / "java").exists():
            candidates.append(_relative_path(project_root, child))
    return sorted(_dedupe(candidates))


def _xml_local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _parse_maven_modules(project_root: Path) -> list[str]:
    pom_path = project_root / "pom.xml"
    if not pom_path.exists():
        return []

    try:
        root = ET.fromstring(pom_path.read_text(encoding="utf-8"))
    except (ET.ParseError, OSError):
        return []

    modules: list[str] = []
    for element in root.iter():
        if _xml_local_name(element.tag) != "module":
            continue
        text = (element.text or "").strip()
        if text:
            modules.append(text.replace("\\", "/").strip("/"))
    return _dedupe(modules)


def _parse_gradle_modules(project_root: Path) -> list[str]:
    settings_files = [project_root / "settings.gradle", project_root / "settings.gradle.kts"]
    for settings_path in settings_files:
        if not settings_path.exists():
            continue
        try:
            content = settings_path.read_text(encoding="utf-8")
        except OSError:
            continue

        modules: list[str] = []
        for quoted in re.findall(r"""["']([^"']+)["']""", content):
            candidate = quoted.strip()
            if not candidate.startswith(":"):
                continue
            modules.append(candidate.lstrip(":").replace(":", "/"))
        if modules:
            return _dedupe(modules)
    return []


def _gradle_command(project_root: Path) -> str:
    if (project_root / "gradlew").exists():
        return "./gradlew"
    if (project_root / "gradlew.bat").exists():
        return "gradlew.bat"
    return "gradle"


def _detect_build(project_root: Path) -> BuildDetection:
    if (project_root / "pom.xml").exists():
        return BuildDetection(
            tool="maven",
            build="mvn -q -DskipTests package",
            test="mvn -q test",
            module_paths=_parse_maven_modules(project_root) or _module_candidates_from_tree(project_root),
        )

    if any((project_root / marker).exists() for marker in ("settings.gradle", "settings.gradle.kts", "build.gradle", "build.gradle.kts", "gradlew", "gradlew.bat")):
        gradle = _gradle_command(project_root)
        return BuildDetection(
            tool="gradle",
            build=f"{gradle} build -x test",
            test=f"{gradle} test",
            module_paths=_parse_gradle_modules(project_root) or _module_candidates_from_tree(project_root),
        )

    return BuildDetection(
        tool="unknown",
        build="java-build-command-required",
        test="java-test-command-required",
        module_paths=_module_candidates_from_tree(project_root),
    )


def _tokenize_module_name(value: str) -> list[str]:
    return [token for token in re.split(r"[-_/]+", value.lower()) if token]


def _sanitize_key(value: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return sanitized or "module"


def _build_module_map(module_paths: list[str]) -> dict[str, list[str]]:
    if len(module_paths) <= 1:
        return {}

    basenames = [Path(module_path).name for module_path in module_paths]
    token_lists = [_tokenize_module_name(name) for name in basenames]
    common_prefix: list[str] = []
    if token_lists:
        shortest = min(len(tokens) for tokens in token_lists)
        for index in range(shortest):
            token = token_lists[0][index]
            if all(tokens[index] == token for tokens in token_lists):
                common_prefix.append(token)
            else:
                break

    module_map: OrderedDict[str, list[str]] = OrderedDict()
    used_keys: set[str] = set()
    for module_path, basename, tokens in zip(module_paths, basenames, token_lists, strict=False):
        trimmed_tokens = tokens[len(common_prefix):] if len(tokens) > len(common_prefix) else tokens
        preferred_name = "_".join(trimmed_tokens) if trimmed_tokens else basename
        key = _sanitize_key(preferred_name)
        if key in used_keys:
            key = _sanitize_key(module_path)
        used_keys.add(key)
        module_map[key] = [module_path]
    return dict(module_map)


def _collect_markdown_files(project_root: Path) -> list[Path]:
    candidates: list[Path] = []
    for name in ("README.md", "README.MD", "readme.md"):
        candidate = project_root / name
        if candidate.exists():
            candidates.append(candidate)
    for root_name in DOC_SCAN_DIRS:
        root = project_root / root_name
        if not root.exists():
            continue
        if root.is_file() and root.suffix.lower() == ".md":
            candidates.append(root)
            continue
        if not root.is_dir():
            continue
        for path in root.rglob("*.md"):
            if any(part in SKIP_DIR_NAMES or part.startswith(".") for part in path.parts):
                continue
            candidates.append(path)
    return sorted({path.resolve(): path for path in candidates}.values(), key=lambda item: _relative_path(project_root, item).lower())


def _keyword_matches(project_root: Path, keywords: tuple[str, ...], limit: int = 6) -> list[str]:
    matches: list[str] = []
    lowered_keywords = tuple(keyword.lower() for keyword in keywords)
    for path in _collect_markdown_files(project_root):
        relative = _relative_path(project_root, path)
        lowered = relative.lower()
        if any(keyword in lowered for keyword in lowered_keywords) or any(keyword in relative for keyword in keywords):
            matches.append(relative)
        if len(matches) >= limit:
            break
    return _dedupe(matches)


def _discover_architecture_paths(project_root: Path) -> list[str]:
    directories = _existing_paths(
        project_root,
        ["docs/architecture", "docs/adr", "architecture", "adr", "design", "docs/design"],
        [],
    )
    files = _existing_paths(
        project_root,
        ["README.md", "docs/README.md", "readme/README.md", "docs/overview.md", "docs/quickstart.md", "readme/quickstart.md"],
        [],
    )
    keyword_files = _keyword_matches(project_root, ARCHITECTURE_KEYWORDS, limit=4) if not (directories or files) else []
    combined = _dedupe(directories + files + keyword_files)
    return combined or ["README.md"]


def _discover_runbook_paths(project_root: Path) -> list[str]:
    directories = _existing_paths(
        project_root,
        ["docs/runbooks", "runbooks", "docs/operations", "operations", "docs/ops", "ops"],
        [],
    )
    keyword_files = _keyword_matches(project_root, RUNBOOK_KEYWORDS, limit=6)
    if directories:
        return directories
    return keyword_files


def _discover_plan_paths(project_root: Path) -> list[str]:
    directories = _existing_paths(
        project_root,
        ["docs/exec-plans", "docs/plans", "plans", "plan", "docs/roadmap", "roadmap"],
        [],
    )
    keyword_files = _keyword_matches(project_root, PLAN_KEYWORDS, limit=6)
    if directories:
        return directories
    return keyword_files


def _expand_markdown_targets(project_root: Path, targets: list[str], keywords: tuple[str, ...], limit: int = 8) -> list[str]:
    expanded: list[str] = []
    lowered_keywords = tuple(keyword.lower() for keyword in keywords)
    for target in targets:
        path = project_root / target
        if path.is_file():
            expanded.append(target)
            continue
        if not path.is_dir():
            continue
        for file_path in sorted(path.rglob("*.md")):
            if any(part in SKIP_DIR_NAMES or part.startswith(".") for part in file_path.parts):
                continue
            relative = _relative_path(project_root, file_path)
            lowered = relative.lower()
            if any(keyword in lowered for keyword in lowered_keywords) or any(keyword in relative for keyword in keywords):
                expanded.append(relative)
            if len(expanded) >= limit:
                break
        if len(expanded) >= limit:
            break
    return _dedupe(expanded)[:limit]


def _doc_hint_name(relative_path: str) -> str:
    lowered = relative_path.lower()
    for patterns, alias in DOC_HINT_ALIASES:
        if any(pattern.lower() in lowered for pattern in patterns) or any(pattern in relative_path for pattern in patterns):
            return alias
    stem = Path(relative_path).stem
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", stem).strip("-").lower()
    return slug or "doc"


def _build_doc_hints(project_root: Path, architecture_paths: list[str], runbook_paths: list[str], plan_paths: list[str]) -> dict[str, list[str]]:
    hints: OrderedDict[str, list[str]] = OrderedDict()

    architecture_files = _expand_markdown_targets(project_root, architecture_paths, ARCHITECTURE_KEYWORDS, limit=4)
    if architecture_files:
        hints["architecture"] = architecture_files

    for runbook_file in _expand_markdown_targets(project_root, runbook_paths, RUNBOOK_KEYWORDS, limit=6):
        key = _doc_hint_name(runbook_file)
        if key in {"readme", "overview", "template"}:
            continue
        hints.setdefault(key, []).append(runbook_file)

    for plan_file in _expand_markdown_targets(project_root, plan_paths, PLAN_KEYWORDS, limit=4):
        key = _doc_hint_name(plan_file)
        if key == "template":
            continue
        hints.setdefault(key, []).append(plan_file)

    return {key: _dedupe(values) for key, values in hints.items()}


def _detect_critical_flows(doc_hints: dict[str, list[str]]) -> list[str]:
    flows: list[str] = []
    lowered_keywords = tuple(keyword.lower() for keyword in RUNBOOK_KEYWORDS)
    for key, values in doc_hints.items():
        if key == "architecture":
            continue
        joined = " ".join(value.lower() for value in values)
        if not any(keyword in key or keyword in joined for keyword in lowered_keywords):
            continue
        flows.append(key)
    return _dedupe(flows)


class JavaLanguageAdapter(LanguageAdapter):
    name = "java"

    def detect(self, project_root: Path) -> bool:
        if (project_root / "pom.xml").exists() or (project_root / "build.gradle").exists() or (project_root / "build.gradle.kts").exists():
            return True
        return any(project_root.rglob("*.java"))

    def analyze(self, project_root: Path, project_config: ProjectConfig) -> dict[str, Any]:
        return analyze_code_entropy(project_root, project_config)

    def build_export(self, payload: dict[str, Any]) -> dict[str, Any]:
        return build_code_entropy_export(payload)

    def scaffold_project(self, project_root: Path, project_id: str, project_name: str) -> LanguageScaffold:
        package_prefixes = discover_internal_package_prefixes(project_root) or ["com.example"]
        build = _detect_build(project_root)
        architecture_paths = _discover_architecture_paths(project_root)
        runbook_paths = _discover_runbook_paths(project_root)
        plan_paths = _discover_plan_paths(project_root)
        doc_hints = _build_doc_hints(project_root, architecture_paths, runbook_paths, plan_paths)
        module_map = _build_module_map(build.module_paths)
        critical_flows = _detect_critical_flows(doc_hints)

        exclude_dirs = _dedupe(
            [
                ".git",
                ".idea",
                ".history",
                ".cursor",
                ".claude",
                ".graphify_python",
                "graphify-out",
                "target",
                "node_modules",
                "build",
                "dist",
                ".gradle",
                "__pycache__",
            ]
        )
        commands = OrderedDict(
            [
                ("build", build.build),
                ("test", build.test),
            ]
        )
        doc_hints_section = _render_array_table("doc_hints", doc_hints)
        commands_section = _render_string_table("commands", dict(commands))
        module_map_section = _render_array_table("module_map", module_map)
        template_text = _load_template(JAVA_CONFIG_TEMPLATE_PATH)
        config_text = _render_template(
            template_text,
            {
                "PROJECT_ID": _toml_string(project_id),
                "PROJECT_NAME": _toml_string(project_name),
                "CRITICAL_FLOWS": _toml_array(critical_flows),
                "ARCHITECTURE_PATHS": _toml_array(architecture_paths),
                "RUNBOOK_PATHS": _toml_array(runbook_paths),
                "PLAN_PATHS": _toml_array(plan_paths),
                "EXCLUDE_DIRS": _toml_array(exclude_dirs),
                "INTERNAL_PACKAGE_PREFIXES": _toml_array(package_prefixes),
                "DOC_HINTS_SECTION": doc_hints_section,
                "COMMANDS_SECTION": commands_section,
                "MODULE_MAP_SECTION": module_map_section,
            },
        ).rstrip() + "\n"

        calibration_template_text = _load_template(JAVA_CALIBRATION_TEMPLATE_PATH)
        calibration_text = _render_template(
            calibration_template_text,
            {
                "CALIBRATION_AUTHOR": _toml_string("entropy-audit init"),
                "CALIBRATION_REASON": _toml_string("bootstrap"),
            },
            allow_unresolved={"CALIBRATION_GENERATED_AT"},
        ).rstrip() + "\n"

        notes = [
            f"Detected build tool: {build.tool}",
            f"Detected Java package prefixes: {', '.join(package_prefixes)}",
            f"Detected build command: {build.build}",
            f"Detected module paths: {', '.join(build.module_paths)}" if build.module_paths else "No explicit multi-module layout detected.",
            f"Detected documentation anchors: architecture={len(architecture_paths)}, runbooks={len(runbook_paths)}, plans={len(plan_paths)}",
            "Add CI exports and invariant checks later when dependency / contract / layering validation is available.",
        ]
        return LanguageScaffold(config_text=config_text, calibration_text=calibration_text, notes=notes)
