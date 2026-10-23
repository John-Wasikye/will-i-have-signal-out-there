"""Tests for building the Lambda zip package."""

import base64
import hashlib
import zipfile

from build_package import build_zip, serving_source_files, sha256_base64


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
