"""Tests for graphql_client_generator.cli."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from graphql_client_generator.cli import main


class TestCLI:
    def test_default_args(self, tmp_path: Path, minimal_schema_path: Path):
        """Test with only required schema argument, default name and output."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        with patch(
            "graphql_client_generator.cli.generate_from_file"
        ) as mock_generate:
            mock_generate.return_value = output_dir / "minimal"
            main([str(minimal_schema_path), "-o", str(output_dir)])
            mock_generate.assert_called_once_with(
                minimal_schema_path,
                minimal_schema_path.stem,
                output_dir,
                as_package=True,
            )

    def test_custom_name(self, tmp_path: Path, minimal_schema_path: Path):
        """Test with custom package name."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        with patch(
            "graphql_client_generator.cli.generate_from_file"
        ) as mock_generate:
            mock_generate.return_value = output_dir / "custom_client"
            main([
                str(minimal_schema_path),
                "-n", "custom_client",
                "-o", str(output_dir),
            ])
            mock_generate.assert_called_once_with(
                minimal_schema_path,
                "custom_client",
                output_dir,
                as_package=True,
            )

    def test_custom_output(self, tmp_path: Path, minimal_schema_path: Path):
        """Test with custom output directory."""
        output_dir = tmp_path / "my_output"
        output_dir.mkdir()
        with patch(
            "graphql_client_generator.cli.generate_from_file"
        ) as mock_generate:
            mock_generate.return_value = output_dir / "minimal"
            main([str(minimal_schema_path), "-o", str(output_dir)])
            call_args = mock_generate.call_args
            assert call_args[0][2] == output_dir

    def test_missing_file(self, tmp_path: Path):
        """Test with a non-existent schema file."""
        missing = tmp_path / "nonexistent.graphqls"
        with pytest.raises(SystemExit) as exc_info:
            main([str(missing)])
        assert exc_info.value.code == 1

    def test_prints_result_path(
        self, tmp_path: Path, minimal_schema_path: Path, capsys
    ):
        """Test that the generated path is printed."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        result_path = output_dir / "minimal"
        with patch(
            "graphql_client_generator.cli.generate_from_file"
        ) as mock_generate:
            mock_generate.return_value = result_path
            main([str(minimal_schema_path), "-o", str(output_dir)])
        captured = capsys.readouterr()
        assert str(result_path) in captured.out

    def test_name_defaults_to_stem(
        self, tmp_path: Path, minimal_schema_path: Path
    ):
        """When no --name is given, package name defaults to schema filename stem."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        with patch(
            "graphql_client_generator.cli.generate_from_file"
        ) as mock_generate:
            mock_generate.return_value = output_dir / "minimal"
            main([str(minimal_schema_path), "-o", str(output_dir)])
            call_args = mock_generate.call_args
            # Package name should be the stem of the schema file
            assert call_args[0][1] == minimal_schema_path.stem

    def test_long_option_names(
        self, tmp_path: Path, minimal_schema_path: Path
    ):
        """Test with long option names --name and --output."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        with patch(
            "graphql_client_generator.cli.generate_from_file"
        ) as mock_generate:
            mock_generate.return_value = output_dir / "my_pkg"
            main([
                str(minimal_schema_path),
                "--name", "my_pkg",
                "--output", str(output_dir),
            ])
            mock_generate.assert_called_once_with(
                minimal_schema_path,
                "my_pkg",
                output_dir,
                as_package=True,
            )


class TestCLIEndpoint:
    """Tests for the URL-based introspection code path."""

    def test_url_calls_generate_from_endpoint(self, tmp_path: Path):
        """When given an http URL, generate_from_endpoint should be called."""
        output_dir = tmp_path / "out"
        output_dir.mkdir()
        with patch(
            "graphql_client_generator.cli.generate_from_endpoint",
            return_value=output_dir / "client",
        ) as mock_gen:
            main(["https://api.example.com/graphql", "-n", "my_client", "-o", str(output_dir)])
        mock_gen.assert_called_once_with(
            "https://api.example.com/graphql", "my_client", output_dir,
            headers=None, as_package=True,
        )

    def test_url_default_name_is_client(self, tmp_path: Path):
        """When no --name is given for a URL, package name defaults to 'client'."""
        output_dir = tmp_path / "out"
        output_dir.mkdir()
        with patch(
            "graphql_client_generator.cli.generate_from_endpoint",
            return_value=output_dir / "client",
        ) as mock_gen:
            main(["https://api.example.com/graphql", "-o", str(output_dir)])
        assert mock_gen.call_args[0][1] == "client"

    def test_header_flag_parsed_and_forwarded(self, tmp_path: Path):
        """--header values should be forwarded as a dict to generate_from_endpoint."""
        output_dir = tmp_path / "out"
        output_dir.mkdir()
        with patch(
            "graphql_client_generator.cli.generate_from_endpoint",
            return_value=output_dir / "client",
        ) as mock_gen:
            main([
                "https://api.example.com/graphql",
                "-H", "Authorization: Bearer tok",
                "-H", "X-Tenant: acme",
                "-o", str(output_dir),
            ])
        _, kwargs = mock_gen.call_args
        assert kwargs["headers"] == {"Authorization": "Bearer tok", "X-Tenant": "acme"}

    def test_fetch_error_exits_with_code_1(self, tmp_path: Path, capsys):
        """A RuntimeError from generate_from_endpoint should print and exit 1."""
        with patch(
            "graphql_client_generator.cli.generate_from_endpoint",
            side_effect=RuntimeError("connection refused"),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main(["https://api.example.com/graphql"])
        assert exc_info.value.code == 1
        assert "connection refused" in capsys.readouterr().err


class TestParseHeaders:
    def test_malformed_header_is_warned_and_skipped(self, capsys):
        """A header string without ':' should emit a warning and be skipped."""
        from graphql_client_generator.cli import _parse_headers
        result = _parse_headers(["BadHeader"])
        assert result == {}
        assert "BadHeader" in capsys.readouterr().err


class TestMain:
    def test_module_entry_point(self):
        """python -m graphql_client_generator --help should exit 0."""
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, "-m", "graphql_client_generator", "--help"],
            capture_output=True,
        )
        assert result.returncode == 0



class TestModuleFlag:
    def test_module_flag_passes_as_package_false(self, tmp_path: Path, minimal_schema_path: Path):
        with patch("graphql_client_generator.cli.generate_from_file") as mock_gen:
            mock_gen.return_value = tmp_path / "test_client"
            main([str(minimal_schema_path), "--module", "-o", str(tmp_path)])
        _, kwargs = mock_gen.call_args
        assert kwargs["as_package"] is False

    def test_no_module_flag_passes_as_package_true(self, tmp_path: Path, minimal_schema_path: Path):
        with patch("graphql_client_generator.cli.generate_from_file") as mock_gen:
            mock_gen.return_value = tmp_path / "test_client"
            main([str(minimal_schema_path), "-o", str(tmp_path)])
        _, kwargs = mock_gen.call_args
        assert kwargs["as_package"] is True
