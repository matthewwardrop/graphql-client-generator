"""Tests for graphql_client_generator._runtime.serialization."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import pytest

from graphql_client_generator._runtime.serialization import (
    serialize_input,
    to_camel_case,
    to_snake_case,
)


# ---------------------------------------------------------------------------
# to_camel_case
# ---------------------------------------------------------------------------


class TestToCamelCase:
    def test_single_word(self):
        assert to_camel_case("name") == "name"

    def test_two_words(self):
        assert to_camel_case("first_name") == "firstName"

    def test_three_words(self):
        assert to_camel_case("get_user_name") == "getUserName"

    def test_already_camel(self):
        # Single word stays the same
        assert to_camel_case("firstName") == "firstName"

    def test_empty_string(self):
        assert to_camel_case("") == ""

    def test_leading_underscore(self):
        # Leading underscore results in empty first part
        result = to_camel_case("_private")
        assert result == "Private"

    def test_all_caps_word(self):
        assert to_camel_case("http_response") == "httpResponse"


# ---------------------------------------------------------------------------
# to_snake_case
# ---------------------------------------------------------------------------


class TestToSnakeCase:
    def test_single_word(self):
        assert to_snake_case("name") == "name"

    def test_camel_case(self):
        assert to_snake_case("firstName") == "first_name"

    def test_multiple_words(self):
        assert to_snake_case("getUserName") == "get_user_name"

    def test_already_snake(self):
        assert to_snake_case("first_name") == "first_name"

    def test_consecutive_caps(self):
        assert to_snake_case("HTTPResponse") == "h_t_t_p_response"

    def test_single_uppercase(self):
        assert to_snake_case("A") == "a"

    def test_empty_string(self):
        assert to_snake_case("") == ""

    def test_all_lowercase(self):
        assert to_snake_case("hello") == "hello"


# ---------------------------------------------------------------------------
# serialize_input
# ---------------------------------------------------------------------------


class Color(Enum):
    RED = "RED"
    BLUE = "BLUE"


@dataclass
class Address:
    street_name: str
    zip_code: str


@dataclass
class UserInput:
    first_name: str
    email: str
    age: int | None = None
    color: Color | None = None
    tags: list[str] | None = None
    address: Address | None = None


class TestSerializeInput:
    def test_none(self):
        assert serialize_input(None) is None

    def test_enum(self):
        assert serialize_input(Color.RED) == "RED"

    def test_list(self):
        result = serialize_input([Color.RED, Color.BLUE])
        assert result == ["RED", "BLUE"]

    def test_empty_list(self):
        assert serialize_input([]) == []

    def test_dict(self):
        result = serialize_input({"key": "value", "nested": None})
        assert result == {"key": "value", "nested": None}

    def test_dataclass_simple(self):
        inp = Address(street_name="Main St", zip_code="12345")
        result = serialize_input(inp)
        assert result == {"streetName": "Main St", "zipCode": "12345"}

    def test_dataclass_with_none_fields(self):
        inp = UserInput(first_name="Alice", email="a@b.com")
        result = serialize_input(inp)
        assert result["firstName"] == "Alice"
        assert result["email"] == "a@b.com"
        assert result["age"] is None

    def test_dataclass_with_enum(self):
        inp = UserInput(first_name="Alice", email="a@b.com", color=Color.RED)
        result = serialize_input(inp)
        assert result["color"] == "RED"

    def test_dataclass_with_list(self):
        inp = UserInput(
            first_name="Alice", email="a@b.com", tags=["admin", "user"]
        )
        result = serialize_input(inp)
        assert result["tags"] == ["admin", "user"]

    def test_dataclass_nested(self):
        addr = Address(street_name="Main St", zip_code="12345")
        inp = UserInput(first_name="Alice", email="a@b.com", address=addr)
        result = serialize_input(inp)
        assert result["address"] == {
            "streetName": "Main St",
            "zipCode": "12345",
        }

    def test_scalar_passthrough(self):
        assert serialize_input(42) == 42
        assert serialize_input("hello") == "hello"
        assert serialize_input(3.14) == 3.14
        assert serialize_input(True) is True

    def test_list_of_dataclasses(self):
        addrs = [
            Address(street_name="A St", zip_code="111"),
            Address(street_name="B St", zip_code="222"),
        ]
        result = serialize_input(addrs)
        assert len(result) == 2
        assert result[0] == {"streetName": "A St", "zipCode": "111"}
        assert result[1] == {"streetName": "B St", "zipCode": "222"}

    def test_dict_with_nested_values(self):
        result = serialize_input({"items": [1, 2, 3], "meta": None})
        assert result == {"items": [1, 2, 3], "meta": None}
