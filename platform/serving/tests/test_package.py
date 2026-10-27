"""Tests for building the Lambda zip package."""

import base64
import hashlib
import re
import zipfile

from build_package import (
    LOCK_PATH,
    REQUIREMENTS_PATH,
    build_zip,
    install_dependencies,
    serving_source_files,
    sha256_base64,
)


def _make_serving_folder(tmp_path):
    serving = tmp_path / "serving"
    (serving / "tests").mkdir(parents=True)
    for name in ("app.py", "duckdb_query.py", "handler.py", "published_files.py"):
        (serving / name).write_text(f"# {name}\n", encoding="utf-8")
    (serving / "build_package.py").write_text("# packaging script\n", encoding="utf-8")
    (serving / "tests" / "test_app.py").write_text("# a test\n", encoding="utf-8")
    (serving / "requirements.txt").write_text("duckdb\n", encoding="utf-8")
    return serving


def _make_dependencies(tmp_path):
    dependencies = tmp_path / "deps"
    (dependencies / "duckdb").mkdir(parents=True)
    (dependencies / "duckdb" / "__init__.py").write_text("# duckdb\n", encoding="utf-8")
    (dependencies / "duckdb" / "__pycache__").mkdir()
    (dependencies / "duckdb" / "__pycache__" / "x.cpython-312.pyc").write_bytes(b"\x00")
    return dependencies


def test_only_the_runtime_python_files_are_packaged(tmp_path):
    serving = _make_serving_folder(tmp_path)

    names = sorted(path.name for path in serving_source_files(serving))

    assert names == ["app.py", "duckdb_query.py", "handler.py", "published_files.py"]


def test_the_zip_holds_the_source_files_and_the_dependencies_at_the_top_level(tmp_path):
    serving = _make_serving_folder(tmp_path)
    dependencies = _make_dependencies(tmp_path)
    output = tmp_path / "function.zip"

    build_zip(serving, dependencies, output)

    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
    assert {"handler.py", "app.py", "duckdb_query.py", "published_files.py"} <= names
    assert "duckdb/__init__.py" in names


def test_tests_and_the_packaging_script_stay_out_of_the_zip(tmp_path):
    serving = _make_serving_folder(tmp_path)
    output = tmp_path / "function.zip"

    build_zip(serving, _make_dependencies(tmp_path), output)

    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
    assert not any(name.startswith("tests") for name in names)
    assert "build_package.py" not in names


def test_compiled_python_caches_stay_out_of_the_zip(tmp_path):
    serving = _make_serving_folder(tmp_path)
    output = tmp_path / "function.zip"

    build_zip(serving, _make_dependencies(tmp_path), output)

    with zipfile.ZipFile(output) as archive:
        assert not any(
            "__pycache__" in name or name.endswith(".pyc") for name in archive.namelist()
        )


def test_the_same_inputs_give_the_same_zip_every_time(tmp_path):
    serving = _make_serving_folder(tmp_path)
    dependencies = _make_dependencies(tmp_path)

    build_zip(serving, dependencies, tmp_path / "first.zip")
    build_zip(serving, dependencies, tmp_path / "second.zip")

    assert (tmp_path / "first.zip").read_bytes() == (tmp_path / "second.zip").read_bytes()


def test_the_checksum_matches_the_format_terraform_expects(tmp_path):
    path = tmp_path / "file.bin"
    path.write_bytes(b"hello")

    expected = base64.b64encode(hashlib.sha256(b"hello").digest()).decode("ascii")

    assert sha256_base64(path) == expected


# --- The same package from every machine, on every day --------------------------------------
#
# A build on 2026-10-22 and one on 2026-10-27 differed: requirements.txt pinned only the four
# packages I chose, so Starlette, which FastAPI pulls in, moved from 1.9.0 to 1.10.0. A build on
# Windows also differed from one on Linux, because pip writes console scripts (bin/fastapi.exe)
# and lists them in each package's RECORD file. Every package is now locked with its hash, and
# the files that depend on the machine stay out of the zip.


def _locked_versions(text):
    return dict(re.findall(r"^([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+!-]+)", text, re.MULTILINE))


def test_every_locked_package_has_an_exact_version_and_a_hash():
    text = LOCK_PATH.read_text(encoding="utf-8")
    blocks = [block for block in re.split(r"\n(?=[A-Za-z0-9])", text) if block[:1].isalnum()]

    assert blocks, "the lock file lists no packages"
    for block in blocks:
        assert re.match(r"^[A-Za-z0-9_.-]+==\S+", block), block.splitlines()[0]
        assert "--hash=sha256:" in block, block.splitlines()[0]


def test_the_lock_keeps_the_versions_i_chose():
    chosen = _locked_versions(REQUIREMENTS_PATH.read_text(encoding="utf-8"))
    locked = _locked_versions(LOCK_PATH.read_text(encoding="utf-8"))

    assert chosen
    for name, version in chosen.items():
        assert locked.get(name) == version, name


def test_the_build_installs_only_the_locked_packages(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("build_package.subprocess.run", lambda args, check: calls.append(args))

    install_dependencies(LOCK_PATH, tmp_path / "deps")

    (args,) = calls
    assert args[args.index("--requirement") + 1] == str(LOCK_PATH)
    assert "--no-deps" in args
    assert "--require-hashes" in args


def test_files_that_depend_on_the_machine_stay_out_of_the_zip(tmp_path):
    serving = _make_serving_folder(tmp_path)
    dependencies = _make_dependencies(tmp_path)
    (dependencies / "bin").mkdir()
    (dependencies / "bin" / "fastapi.exe").write_bytes(b"MZ")
    info = dependencies / "fastapi-0.143.0.dist-info"
    info.mkdir()
    (info / "RECORD").write_text("bin/fastapi.exe,,\n", encoding="utf-8")
    (info / "METADATA").write_text("Name: fastapi\n", encoding="utf-8")
    output = tmp_path / "function.zip"

    build_zip(serving, dependencies, output)

    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
    assert not any(name.startswith("bin/") for name in names)
    assert "fastapi-0.143.0.dist-info/RECORD" not in names
    # Packages read their own version from METADATA, so it stays.
    assert "fastapi-0.143.0.dist-info/METADATA" in names
