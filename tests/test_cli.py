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
            "graphql_client_generator.cli.generate"
        ) as mock_generate:
            mock_generate.return_value = output_dir / "minimal"
            main([str(minimal_schema_path), "-o", str(output_dir)])
            mock_generate.assert_called_once_with(
                minimal_schema_path,
                minimal_schema_path.stem,
                output_dir,
            )

    def test_custom_name(self, tmp_path: Path, minimal_schema_path: Path):
        """Test with custom package name."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        with patch(
            "graphql_client_generator.cli.generate"
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
            )

    def test_custom_output(self, tmp_path: Path, minimal_schema_path: Path):
        """Test with custom output directory."""
        output_dir = tmp_path / "my_output"
        output_dir.mkdir()
        with patch(
            "graphql_client_generator.cli.generate"
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
            "graphql_client_generator.cli.generate"
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
            "graphql_client_generator.cli.generate"
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
            "graphql_client_generator.cli.generate"
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
            )
