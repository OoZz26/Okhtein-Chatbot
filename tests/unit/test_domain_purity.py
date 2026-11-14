"""Enforces the dependency rule: the domain imports no SDK, framework or outer layer."""

import ast
from pathlib import Path

DOMAIN_DIR = Path(__file__).parents[2] / "app" / "domain"
FORBIDDEN = {"openai", "fastapi", "redis", "sqlalchemy", "httpx", "asyncpg", "pydantic", "starlette"}
FORBIDDEN_APP_LAYERS = {"app.infra", "app.api", "app.services", "app.bootstrap"}


def imported_modules(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_domain_modules_exist() -> None:
    assert list(DOMAIN_DIR.rglob("*.py")), "no domain files found; the test would pass vacuously"


def test_domain_imports_no_third_party_sdk_or_outer_layer() -> None:
    violations = []
    for path in DOMAIN_DIR.rglob("*.py"):
        for module in imported_modules(path):
            top_level = module.split(".")[0]
            is_outer_layer = any(module == m or module.startswith(m + ".") for m in FORBIDDEN_APP_LAYERS)
            if top_level in FORBIDDEN or is_outer_layer:
                violations.append(f"{path.name} imports {module}")
    assert not violations, violations
