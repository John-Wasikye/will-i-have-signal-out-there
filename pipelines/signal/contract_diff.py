"""Contract diff (C8): check a source's fields against its data contract before loading.

An upstream change should stop the run before anything is loaded, and name the field that
changed (FR-14, ADR 0018). The contract lists lake columns. A column read straight from the
source names that source field in its `upstreamField` custom property, and may give the
source's own type in `upstreamType`. Columns the loader adds have neither, so they are not part
of the source's schema.

A removed field or a changed type is breaking. A renamed field shows as one removed and one
added. An added field is listed but not breaking: the loader reads only the fields it knows.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

JSON_TYPES = {
    bool: "boolean",
    int: "integer",
    float: "number",
    str: "string",
    list: "array",
    dict: "object",
}


class BreakingSchemaChange(Exception):
    """The source's fields no longer match its contract."""


@dataclass(frozen=True)
class SchemaDiff:
    """Fields added to, removed from, or changed in the source, compared with its contract.

    `changed` holds (field, contract type, observed type) for each type that differs.
    """

    added: tuple[str, ...]
    removed: tuple[str, ...]
    changed: tuple[tuple[str, str, str], ...]

    @property
    def is_breaking(self) -> bool:
        """True when a field the contract expects is gone or has another type."""
        return bool(self.removed or self.changed)


def load_contract(path: Path) -> dict[str, str | None]:
    """Return each source field the contract reads, with its source type or None if unstated."""
    contract = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    fields: dict[str, str | None] = {}
    for table in contract.get("schema", []):
        for column in table.get("properties", []):
            custom = {
                item["property"]: item["value"] for item in column.get("customProperties", [])
            }
            if "upstreamField" in custom:
                fields[custom["upstreamField"]] = custom.get("upstreamType")
    if not fields:
        raise ValueError(f"{path}: the contract has no upstreamField, so there is nothing to check")
    return fields


def diff_schema(expected: Mapping[str, str | None], observed: Mapping[str, str]) -> SchemaDiff:
    """Compare the fields a contract expects with the fields a source file has."""
    changed = tuple(
        (name, expected_type, observed[name])
        for name, expected_type in expected.items()
        if expected_type is not None
        and not _type_matches(expected_type, observed.get(name, "null"))
    )
    return SchemaDiff(
        added=tuple(sorted(set(observed) - set(expected))),
        removed=tuple(sorted(set(expected) - set(observed))),
        changed=tuple(sorted(changed)),
    )


def _type_matches(expected_type: str, observed_type: str) -> bool:
    # A field that is null throughout says nothing about its type. JSON writes 0.0 as 0, so a
    # number field can arrive holding only whole numbers.
    if observed_type in ("null", expected_type):
        return True
    return expected_type == "number" and observed_type == "integer"


def assert_no_breaking_change(diff: SchemaDiff, source: str) -> None:
    """Raise BreakingSchemaChange naming every difference when the diff is breaking."""
    if not diff.is_breaking:
        return
    parts = [f"removed {name}" for name in diff.removed]
    parts += [f"{name} changed from {was} to {now}" for name, was, now in diff.changed]
    parts += [f"added {name}" for name in diff.added]
    raise BreakingSchemaChange(
        f"{source}: the source no longer matches its contract: {', '.join(parts)}"
    )


def observed_schema_from_records(records: Iterable[Mapping[str, object]]) -> dict[str, str]:
    """Read each field's JSON type from parsed records, such as a JSON source file.

    Nulls say nothing about a type, so they are skipped, and a field that is null in every
    record has the type "null": it is present, and its type is not compared. Integers and
    decimals in one field are a number. Any other mix is "mixed", which matches no contract type.
    """
    seen: dict[str, set[str]] = {}
    count = 0
    for record in records:
        count += 1
        for name, value in record.items():
            types = seen.setdefault(name, set())
            if value is not None:
                types.add(JSON_TYPES[type(value)])
    if count == 0:
        raise ValueError("no records, so the source's fields cannot be read")
    return {name: _single_type(types) for name, types in seen.items()}


def _single_type(types: set[str]) -> str:
    if not types:
        return "null"
    if types == {"integer", "number"}:
        return "number"
    return types.pop() if len(types) == 1 else "mixed"
