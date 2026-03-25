"""Tests for graphql_client_generator.generator."""

from __future__ import annotations

from pathlib import Path

import pytest

from graphql_client_generator.generator import _to_pascal_case, generate


# ---------------------------------------------------------------------------
# _to_pascal_case
# ---------------------------------------------------------------------------


class TestToPascalCase:
    def test_snake_case(self):
        assert _to_pascal_case("my_client") == "MyClient"

    def test_kebab_case(self):
        assert _to_pascal_case("my-client") == "MyClient"

    def test_single_word(self):
        assert _to_pascal_case("client") == "Client"

    def test_already_pascal(self):
        # "Client" -> split on _ -> ["Client"] -> capitalize -> "Client"
        assert _to_pascal_case("Client") == "Client"

    def test_multiple_parts(self):
        assert _to_pascal_case("my_cool_api_client") == "MyCoolApiClient"

    def test_mixed_kebab_snake(self):
        assert _to_pascal_case("my-cool_client") == "MyCoolClient"

    def test_empty_string(self):
        assert _to_pascal_case("") == ""


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------


class TestGenerate:
    def test_creates_package_directory(
        self, tmp_path: Path, minimal_schema_path: Path
    ):
        result = generate(minimal_schema_path, "test_client", tmp_path)
        assert result.exists()
        assert result.is_dir()
        assert result == tmp_path / "test_client"

    def test_creates_all_files(
        self, tmp_path: Path, minimal_schema_path: Path
    ):
        pkg = generate(minimal_schema_path, "test_client", tmp_path)
        expected_files = [
            "__init__.py",
            "enums.py",
            "inputs.py",
            "models.py",
            "client.py",
            "pyproject.toml",
        ]
        for fname in expected_files:
            assert (pkg / fname).exists(), f"Missing file: {fname}"

    def test_copies_runtime(self, tmp_path: Path, minimal_schema_path: Path):
        pkg = generate(minimal_schema_path, "test_client", tmp_path)
        runtime_dir = pkg / "_runtime"
        assert runtime_dir.exists()
        assert runtime_dir.is_dir()
        assert (runtime_dir / "__init__.py").exists() or (
            runtime_dir / "client.py"
        ).exists()

    def test_class_names_derived_from_package_name(
        self, tmp_path: Path, minimal_schema_path: Path
    ):
        pkg = generate(minimal_schema_path, "test_client", tmp_path)
        client_code = (pkg / "client.py").read_text()
        assert "class TestClientClient(" in client_code

        models_code = (pkg / "models.py").read_text()
        assert "TestClientSchema = _TestClientSchema()" in models_code

    def test_enums_file_content(
        self, tmp_path: Path, minimal_schema_path: Path
    ):
        pkg = generate(minimal_schema_path, "test_client", tmp_path)
        code = (pkg / "enums.py").read_text()
        assert "class Role(Enum):" in code

    def test_inputs_file_content(
        self, tmp_path: Path, minimal_schema_path: Path
    ):
        pkg = generate(minimal_schema_path, "test_client", tmp_path)
        code = (pkg / "inputs.py").read_text()
        assert "class CreateUserInput:" in code

    def test_idempotent_regeneration(
        self, tmp_path: Path, minimal_schema_path: Path
    ):
        """Running generate twice should succeed (overwrites existing)."""
        generate(minimal_schema_path, "test_client", tmp_path)
        pkg = generate(minimal_schema_path, "test_client", tmp_path)
        assert pkg.exists()
        assert (pkg / "client.py").exists()

    def test_pyproject_content(
        self, tmp_path: Path, minimal_schema_path: Path
    ):
        pkg = generate(minimal_schema_path, "test_client", tmp_path)
        code = (pkg / "pyproject.toml").read_text()
        assert 'name = "test_client"' in code

    def test_init_imports_client(
        self, tmp_path: Path, minimal_schema_path: Path
    ):
        pkg = generate(minimal_schema_path, "test_client", tmp_path)
        code = (pkg / "__init__.py").read_text()
        assert "TestClientClient" in code

    def test_kebab_case_package_name(
        self, tmp_path: Path, minimal_schema_path: Path
    ):
        pkg = generate(minimal_schema_path, "my-api", tmp_path)
        assert pkg.name == "my-api"
        client_code = (pkg / "client.py").read_text()
        assert "class MyApiClient(" in client_code
