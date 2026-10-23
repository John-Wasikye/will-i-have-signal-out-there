"""The API serves exactly the routes in its contract, docs/platform/openapi-serving-template.yaml.

API Gateway passes every path straight to the app, so the paths here are the paths the site
calls. The site has the matching test, app/src/lib/api.test.ts: it checks each address it
builds against the same file. If either side drifts from the contract, a unit test fails.
"""

from pathlib import Path

import yaml

import app as serving_app

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT = REPO_ROOT / "docs" / "platform" / "openapi-serving-template.yaml"
METHODS = {"get", "put", "post", "delete", "patch", "head", "options"}


def _routes(spec: dict) -> set[tuple[str, str]]:
    return {
        (path, method)
        for path, operations in spec["paths"].items()
        for method in operations
        if method in METHODS
    }


def test_the_app_serves_exactly_the_routes_in_the_contract():
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))

    assert _routes(serving_app.app.openapi()) == _routes(contract)
