"""Check repository rules that can be enforced without external tooling."""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".cfg",
    ".conf",
    ".csv",
    ".example",
    ".html",
    ".ini",
    ".ipynb",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".properties",
    ".py",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".tsv",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
SPECIAL_TEXT_NAMES = {"Makefile", ".dockerignore", ".gitignore"}
SCRIPT_SUFFIXES = {".js", ".jsx", ".ts", ".tsx"}

SECRET_ASSIGNMENT = re.compile(
    r"""(?i)(?:"|')?\b[A-Z][A-Z0-9_]*(?:API[_-]?KEY|ACCESS[_-]?KEY|"""
    r"""CLIENT[_-]?SECRET|ENCRYPTION[_-]?KEY|FERNET[_-]?KEY|PASSWORD|PASSWD|"""
    r"PRIVATE[_-]?KEY|SE"
    r"""CRET(?:[_-]?ACCESS)?(?:[_-]?KEY)?|TOKEN)(?:"|')?\s*[:=]\s*"""
    r"(?P<value>[^#\r\n]*)"
)
CREDENTIAL_URL = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^/\s:@]*:(?P<value>[^@\s]+)@")
KNOWN_CREDENTIAL_PATTERN = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"\b(?:AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,}|"
    r"gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|"
    r"hf_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,})\b"
)
GIGSIM_TEXT_IMPORT = re.compile(
    r"""(?im)^\s*(?:import|export)\b[^\r\n]*\bfrom\s*["']"""
    r"""(?:gigsim|(?:\.\.?/)+gigsim)(?:/|["'])|"""
    r"""^\s*(?:import|require)\s*\(?\s*["']"""
    r"""(?:gigsim|(?:\.\.?/)+gigsim)(?:/|["'])"""
)
QUOTED_TEXT = re.compile(r"""(["'`])(?P<value>.*?)(?<!\\)\1""")
SCRIPT_ASSIGNMENT_PATTERN = re.compile(
    r"""(?im)^\s*(?:(?:const|let|var)\s+)?[\w$]*prompt[\w$]*\s*"""
    r"""(?:\s*:\s*[^=]+)?=\s*(["'`])(?P<value>.*)\1"""
)
PLACEHOLDER_VALUES = {
    "",
    "changeme",
    "example",
    "none",
    "null",
    "placeholder",
    "replace_me",
    "todo",
    "your_value",
}

NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?%?(?![\w.])")
RESULT_LANGUAGE = re.compile(
    r"\b(?:accuracy|benchmark|cost savings|f1(?:[- ]score)?|latency|metric|"
    r"precision|recall|response time|score|success rate|throughput)\b|"
    r"%|\b(?:milliseconds?|ms|seconds?)\b",
    re.IGNORECASE,
)
PROMPT_MARKERS = (
    ("you", "are"),
    ("your", "task"),
    ("system", "prompt"),
    ("follow", "these", "instructions"),
    ("act", "as"),
    ("write", "a", "proposal"),
)


def _is_placeholder(value: str) -> bool:
    value = value.strip().split("#", 1)[0].strip().strip("'\"").strip()
    lowered = value.lower()
    return (
        lowered in PLACEHOLDER_VALUES
        or lowered.startswith(("your_", "${"))
        or set(lowered) <= {"*", "x"}
    )


def secret_pattern_lines(source: str) -> list[int]:
    violations = []
    for line_number, line in enumerate(source.splitlines(), start=1):
        if KNOWN_CREDENTIAL_PATTERN.search(line):
            violations.append(line_number)
            continue
        assignment = SECRET_ASSIGNMENT.search(line)
        url = CREDENTIAL_URL.search(line)
        assignment_is_reference = assignment and line[: assignment.start()].endswith("${")
        if (assignment and not assignment_is_reference and not _is_placeholder(assignment.group("value"))) or (
            url and not _is_placeholder(url.group("value"))
        ):
            violations.append(line_number)
    return violations


def gigsim_import_lines(source: str) -> list[int]:
    tree = ast.parse(source)
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            alias.name == "gigsim" or alias.name.startswith("gigsim.") for alias in node.names
        ) or isinstance(node, ast.ImportFrom) and node.module and (
            node.module == "gigsim" or node.module.startswith("gigsim.")
        ):
            violations.append(node.lineno)
    return sorted(set(violations))


def gigsim_text_import_lines(source: str) -> list[int]:
    return sorted(
        {
            source.count("\n", 0, match.start()) + 1
            for match in GIGSIM_TEXT_IMPORT.finditer(source)
        }
    )


def _target_names(target: ast.expr) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [name for item in target.elts for name in _target_names(item)]
    return []


def _string_literals(node: ast.AST) -> list[str]:
    return [
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str) and child.value.strip()
    ]


def _has_prompt_marker(value: str) -> bool:
    words = re.findall(r"[a-z]+", value.lower())
    return any(
        tuple(words[index : index + len(marker)]) == marker
        for marker in PROMPT_MARKERS
        for index in range(len(words) - len(marker) + 1)
    )


def _looks_like_prompt(value: str) -> bool:
    return len(value.strip()) >= 20 or _has_prompt_marker(value)


def inline_prompt_lines(source: str) -> list[int]:
    tree = ast.parse(source)
    violations = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            names = [name for target in node.targets for name in _target_names(target)]
            if any("prompt" in name.lower() for name in names) and any(
                _looks_like_prompt(value) for value in _string_literals(node.value)
            ):
                violations.add(node.lineno)
        elif isinstance(node, ast.AnnAssign):
            if (
                any("prompt" in name.lower() for name in _target_names(node.target))
                and node.value
                and any(_looks_like_prompt(value) for value in _string_literals(node.value))
            ):
                violations.add(node.lineno)
        elif isinstance(node, ast.Call):
            call_name = ast.unparse(node.func).lower()
            if "prompt" in call_name and any(
                _looks_like_prompt(value) for value in _string_literals(node)
            ):
                violations.add(node.lineno)
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and _has_prompt_marker(node.value)
        ):
            violations.add(node.lineno)
    return sorted(violations)


def inline_prompt_text_lines(source: str) -> list[int]:
    violations = set()
    for match in SCRIPT_ASSIGNMENT_PATTERN.finditer(source):
        if _looks_like_prompt(match.group("value")):
            violations.add(source.count("\n", 0, match.start()) + 1)
    for match in QUOTED_TEXT.finditer(source):
        if _has_prompt_marker(match.group("value")):
            violations.add(source.count("\n", 0, match.start()) + 1)
    return sorted(violations)


def _number_value(token: str) -> Decimal | None:
    try:
        value = Decimal(token.rstrip("%"))
    except InvalidOperation:
        return None
    if token.endswith("%"):
        value /= 100
    return value.normalize()


def unbacked_readme_numbers(readme: str, result_files: dict[str, str]) -> list[tuple[int, str]]:
    result_numbers = set()
    for name, contents in result_files.items():
        for token in NUMBER.findall(f"{name}\n{contents}"):
            normalized = _number_value(token)
            if normalized is not None:
                result_numbers.add(normalized)

    violations = []
    for line_number, line in enumerate(readme.splitlines(), start=1):
        if re.match(r"^\s*\d+[.)]\s", line) or not RESULT_LANGUAGE.search(line):
            continue
        for token in NUMBER.findall(line):
            normalized = _number_value(token)
            if normalized is not None and normalized not in result_numbers:
                violations.append((line_number, token))
    return violations


def _tracked_paths() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return set()
    return {path for path in result.stdout.decode("utf-8").split("\0") if path}


def _repository_text_files(tracked_paths: set[str]) -> list[Path]:
    excluded = {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "__pycache__", "node_modules"}
    paths = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(part in excluded for part in relative.parts):
            continue
        if relative.parts[:2] == ("data", "processed"):
            continue
        if relative.parts[:2] == ("data", "raw") and path.name != "README.md":
            continue
        if (
            path.name.startswith(".env")
            and path.name != ".env.example"
            and relative.as_posix() not in tracked_paths
        ):
            continue
        if (
            path.name.startswith(".env")
            or path.suffix.lower() in TEXT_SUFFIXES
            or path.name in SPECIAL_TEXT_NAMES
            or path.name.startswith("Dockerfile.")
        ):
            paths.append(path)
    return paths


def check_repository() -> list[str]:
    violations = []
    text_files = _repository_text_files(_tracked_paths())

    for path in text_files:
        relative = path.relative_to(ROOT)
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        for line_number in secret_pattern_lines(source):
            violations.append(f"{relative}:{line_number}: possible committed secret")

        if relative.parts[0] in {"agent", "rag", "apps"}:
            is_prompt_file = relative.parts[:2] == ("agent", "prompts")
            try:
                if path.suffix == ".py":
                    import_lines = gigsim_import_lines(source)
                    prompt_lines = [] if is_prompt_file else inline_prompt_lines(source)
                elif path.suffix in SCRIPT_SUFFIXES:
                    import_lines = gigsim_text_import_lines(source)
                    prompt_lines = [] if is_prompt_file else inline_prompt_text_lines(source)
                else:
                    continue
                for line_number in import_lines:
                    violations.append(
                        f"{relative}:{line_number}: import from gigsim; use the marketplace adapter"
                    )
                for line_number in prompt_lines:
                    violations.append(
                        f"{relative}:{line_number}: inline prompt; move it to agent/prompts/"
                    )
            except SyntaxError as error:
                violations.append(f"{relative}:{error.lineno}: cannot parse Python source")

    results_dir = ROOT / "evals" / "results"
    result_files = {}
    if results_dir.exists():
        for path in results_dir.rglob("*"):
            if path.is_file() and path.name != ".gitkeep":
                try:
                    result_files[path.relative_to(ROOT).as_posix()] = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
    readme = ROOT / "README.md"
    if readme.exists():
        for line_number, token in unbacked_readme_numbers(
            readme.read_text(encoding="utf-8"), result_files
        ):
            violations.append(
                f"README.md:{line_number}: reported value {token} has no match in evals/results/"
            )
    return violations


def main() -> int:
    violations = check_repository()
    if violations:
        print("Repository rule violations:")
        for violation in violations:
            print(f"- {violation}")
        return 1
    print("Repository rules passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
