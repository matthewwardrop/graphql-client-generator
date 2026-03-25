"""Tests for graphql_client_generator.generator."""

from __future__ import annotations

from pathlib import Path

import pytest

from graphql_client_generator.generator import _to_pascal_case, generate_from_file


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
# generate_from_file
# ---------------------------------------------------------------------------


class TestGenerate:
    def test_creates_package_directory(
        self, tmp_path: Path, minimal_schema_path: Path
    ):
        result = generate_from_file(minimal_schema_path, "test_client", tmp_path)
        assert result.exists()
        assert result.is_dir()
        assert result == tmp_path / "test-client"

    def test_creates_all_files(
        self, tmp_path: Path, minimal_schema_path: Path
    ):
        pkg = generate_from_file(minimal_schema_path, "test_client", tmp_path)
        module = pkg / "test_client"
        for fname in ("__init__.py", "enums.py", "inputs.py", "outputs.py", "schema.py", "client.py"):
            assert (module / fname).exists(), f"Missing file: {fname}"
        assert (pkg / "pyproject.toml").exists()

    def test_copies_runtime(self, tmp_path: Path, minimal_schema_path: Path):
        pkg = generate_from_file(minimal_schema_path, "test_client", tmp_path)
        runtime_dir = pkg / "test_client" / "_runtime"
        assert runtime_dir.exists()
        assert runtime_dir.is_dir()
        assert (runtime_dir / "__init__.py").exists() or (
            runtime_dir / "client.py"
        ).exists()

    def test_class_names_derived_from_package_name(
        self, tmp_path: Path, minimal_schema_path: Path
    ):
        pkg = generate_from_file(minimal_schema_path, "test_client", tmp_path)
        module = pkg / "test_client"
        client_code = (module / "client.py").read_text()
        assert "class TestClientClient(" in client_code

        schema_code = (module / "schema.py").read_text()
        assert "TestClientSchema = _TestClientSchema()" in schema_code

    def test_enums_file_content(
        self, tmp_path: Path, minimal_schema_path: Path
    ):
        pkg = generate_from_file(minimal_schema_path, "test_client", tmp_path)
        code = (pkg / "test_client" / "enums.py").read_text()
        assert "class Role(Enum):" in code

    def test_inputs_file_content(
        self, tmp_path: Path, minimal_schema_path: Path
    ):
        pkg = generate_from_file(minimal_schema_path, "test_client", tmp_path)
        code = (pkg / "test_client" / "inputs.py").read_text()
        assert "class CreateUserInput:" in code

    def test_idempotent_regeneration(
        self, tmp_path: Path, minimal_schema_path: Path
    ):
        """Running generate_from_file twice should succeed (overwrites existing)."""
        generate_from_file(minimal_schema_path, "test_client", tmp_path)
        pkg = generate_from_file(minimal_schema_path, "test_client", tmp_path)
        assert pkg.exists()
        assert (pkg / "test_client" / "client.py").exists()

    def test_pyproject_content(
        self, tmp_path: Path, minimal_schema_path: Path
    ):
        pkg = generate_from_file(minimal_schema_path, "test_client", tmp_path)
        code = (pkg / "pyproject.toml").read_text()
        assert 'name = "test-client"' in code

    def test_init_imports_client(
        self, tmp_path: Path, minimal_schema_path: Path
    ):
        pkg = generate_from_file(minimal_schema_path, "test_client", tmp_path)
        code = (pkg / "test_client" / "__init__.py").read_text()
        assert "TestClientClient" in code

    def test_init_has_regen_command(
        self, tmp_path: Path, minimal_schema_path: Path
    ):
        pkg = generate_from_file(minimal_schema_path, "test_client", tmp_path)
        code = (pkg / "test_client" / "__init__.py").read_text()
        assert "To regenerate:" in code
        assert "graphql_client_generator" in code
        assert "test_client" in code

    def test_kebab_case_package_name(
        self, tmp_path: Path, minimal_schema_path: Path
    ):
        pkg = generate_from_file(minimal_schema_path, "my-api", tmp_path)
        assert pkg.name == "my-api"
        client_code = (pkg / "my_api" / "client.py").read_text()
        assert "class MyApiClient(" in client_code


class TestGenerateFromEndpoint:
    def test_calls_fetch_and_generate_from_text(self, tmp_path: Path):
        from unittest.mock import patch
        from graphql_client_generator.generator import generate_from_endpoint

        with (
            patch(
                "graphql_client_generator.generator.fetch_schema_sdl",
                return_value="type Query { ping: String }",
            ) as mock_fetch,
            patch(
                "graphql_client_generator.generator.generate_from_text",
                return_value=tmp_path / "client",
            ) as mock_gen,
        ):
            result = generate_from_endpoint(
                "https://api.example.com/graphql",
                "client",
                tmp_path,
                headers={"Authorization": "Bearer tok"},
            )

        mock_fetch.assert_called_once_with(
            "https://api.example.com/graphql",
            session=None,
            headers={"Authorization": "Bearer tok"},
        )
        mock_gen.assert_called_once_with(
            "type Query { ping: String }", "client", tmp_path, True,
            regen_command=f"python -m graphql_client_generator https://api.example.com/graphql -n client -o {tmp_path}",
        )
        assert result == tmp_path / "client"

    def test_module_flag_in_regen_command(self, tmp_path: Path):
        from unittest.mock import patch
        from graphql_client_generator.generator import generate_from_endpoint

        with (
            patch(
                "graphql_client_generator.generator.fetch_schema_sdl",
                return_value="type Query { ping: String }",
            ),
            patch(
                "graphql_client_generator.generator.generate_from_text",
                return_value=tmp_path / "client",
            ) as mock_gen,
        ):
            generate_from_endpoint(
                "https://api.example.com/graphql",
                "client",
                tmp_path,
                as_package=False,
            )

        _, kwargs = mock_gen.call_args
        assert "--module" in kwargs["regen_command"]


class TestModuleMode:
    def test_no_pyproject_when_as_package_false(
        self, tmp_path: Path, minimal_schema_path: Path
    ):
        pkg = generate_from_file(minimal_schema_path, "test_client", tmp_path, as_package=False)
        assert not (pkg / "pyproject.toml").exists()

    def test_python_files_present_when_as_package_false(
        self, tmp_path: Path, minimal_schema_path: Path
    ):
        # module mode: files go directly in the project dir (no nesting)
        pkg = generate_from_file(minimal_schema_path, "test_client", tmp_path, as_package=False)
        assert pkg == tmp_path / "test_client"
        for fname in ("__init__.py", "enums.py", "inputs.py", "outputs.py", "schema.py", "client.py"):
            assert (pkg / fname).exists(), f"Missing file: {fname}"
        assert (pkg / "_runtime").is_dir()

    def test_pyproject_present_by_default(
        self, tmp_path: Path, minimal_schema_path: Path
    ):
        pkg = generate_from_file(minimal_schema_path, "test_client", tmp_path)
        assert (pkg / "pyproject.toml").exists()
