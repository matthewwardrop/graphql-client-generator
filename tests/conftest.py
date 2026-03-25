"""Shared test fixtures with simple GraphQL schemas."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from graphql_client_generator.parser import parse_schema

# ---------------------------------------------------------------------------
# Schema strings
# ---------------------------------------------------------------------------

MINIMAL_SCHEMA = """\
type Query {
  user(id: ID!): User
  users(first: Int = 10): [User!]!
}

type Mutation {
  createUser(input: CreateUserInput!): User!
}

enum Role { ADMIN USER GUEST }

interface Node { id: ID! }

type User implements Node {
  id: ID!
  name: String!
  email: String
  role: Role!
  posts: [Post!]!
}

type Post implements Node {
  id: ID!
  title: String!
  body: String
  author: User!
}

input CreateUserInput {
  name: String!
  email: String
  role: Role!
}

union SearchResult = User | Post
"""

ONEOF_SCHEMA = """\
directive @oneOf on INPUT_OBJECT

type Query { search(filter: SearchFilter!): String }

input SearchFilter @oneOf {
  byName: String
  byId: ID
}
"""

SCALAR_SCHEMA = """\
scalar DateTime
scalar JSON

type Query {
  event(id: ID!): Event
}

type Event {
  id: ID!
  name: String!
  timestamp: DateTime!
  metadata: JSON
}
"""

EMPTY_SCHEMA = """\
type Query {
  hello: String
}
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def minimal_schema_path(tmp_path: Path) -> Path:
    p = tmp_path / "minimal.graphqls"
    p.write_text(MINIMAL_SCHEMA)
    return p


@pytest.fixture()
def minimal_schema(minimal_schema_path: Path):
    return parse_schema(minimal_schema_path)


@pytest.fixture()
def oneof_schema_path(tmp_path: Path) -> Path:
    p = tmp_path / "oneof.graphqls"
    p.write_text(ONEOF_SCHEMA)
    return p


@pytest.fixture()
def oneof_schema(oneof_schema_path: Path):
    return parse_schema(oneof_schema_path)


@pytest.fixture()
def scalar_schema_path(tmp_path: Path) -> Path:
    p = tmp_path / "scalar.graphqls"
    p.write_text(SCALAR_SCHEMA)
    return p


@pytest.fixture()
def scalar_schema(scalar_schema_path: Path):
    return parse_schema(scalar_schema_path)


@pytest.fixture()
def empty_schema_path(tmp_path: Path) -> Path:
    p = tmp_path / "empty.graphqls"
    p.write_text(EMPTY_SCHEMA)
    return p


@pytest.fixture()
def empty_schema(empty_schema_path: Path):
    return parse_schema(empty_schema_path)
