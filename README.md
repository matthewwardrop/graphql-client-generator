# GraphQL Client Generator

Generate typed, tab-completable Python clients from GraphQL schema files.

## Installation

```bash
pip install graphql-client-generator
```

Requires Python >= 3.10.

## Quick Start

Given a schema like `bookstore.graphqls`:

```graphql
type Query {
  book(id: ID!): Book
  books(limit: Int = 10): [Book!]!
  genres: [Genre!]!
}

type Mutation {
  addBook(input: AddBookInput!): Book!
}

type Book {
  id: ID!
  title: String!
  isbn: String
  pageCount: Int
  author: Author!
  reviews: [Review!]!
}

type Author {
  id: ID!
  name: String!
  books: [Book!]!
}

type Review {
  id: ID!
  rating: Int!
  text: String
}

type Genre {
  id: ID!
  name: String!
  description: String
}

input AddBookInput {
  title: String!
  authorId: ID!
  isbn: String
}
```

### Generate a client from a local schema file

```bash
python -m graphql_client_generator bookstore.graphqls
```

This produces a standalone Python package (`bookstore/`) with typed models,
a client class, and a query builder.

To embed the generated client inside an existing package instead, pass
`--module` to skip the `pyproject.toml`:

```bash
python -m graphql_client_generator bookstore.graphqls --module
```

### Generate a client from a live endpoint

Pass an `http://` or `https://` URL instead of a file path and the schema is
fetched automatically via GraphQL introspection:

```bash
python -m graphql_client_generator https://api.example.com/graphql -n bookstore
```

Use `-H` (repeatable) to add HTTP headers - useful for authenticated endpoints:

```bash
python -m graphql_client_generator https://api.example.com/graphql \
    -H "Authorization: Bearer $TOKEN" \
    -n bookstore
```

### Generate from a notebook or script

`generate_from_endpoint` lets you pass a `requests.Session` directly, so any
auth, cookies, or TLS settings you have already configured are reused:

```python
import requests
import graphql_client_generator as gcg

session = requests.Session()
session.headers["Authorization"] = "Bearer <token>"

gcg.generate_from_endpoint(
    "https://api.example.com/graphql",
    name="bookstore",
    session=session,
    # as_package=False  # omit pyproject.toml when embedding in an existing package
)
```

### CLI options

| Flag | Description | Default |
|------|-------------|---------|
| `-n`, `--name` | Package name | Schema filename stem (file) or `client` (URL) |
| `-o`, `--output` | Output directory | Current directory |
| `--module` | Emit Python files only, no `pyproject.toml` | Off |
| `-H`, `--header` | HTTP header for introspection (`Name: Value`), repeatable | |

### Use the generated client

```python
from bookstore import BookstoreClient, BookstoreSchema, Variable
from bookstore.models import Book, Author

client = BookstoreClient("https://api.example.com/graphql")
```

## Query Builder

The generated `BookstoreSchema` object provides a typed, tab-completable
interface for building GraphQL queries. Every field from the schema is
available as an attribute with full IDE support.

### Syntax

| Syntax | Meaning |
|--------|---------|
| `Schema.field` | Select a field |
| `Schema.field(arg=val)` | Pass arguments to a field |
| `selector[field1, field2]` | Select sub-fields |
| `selector.as_("alias")` | Alias a field |
| `Variable.name` | Reference a query variable |
| `Schema[...]` or `Schema(...)` | Build a complete query |

### Examples

**Basic query:**

```python
result = client.query(
    BookstoreSchema[
        BookstoreSchema.book(id=42)[
            Book.title,
            Book.isbn,
        ],
    ],
)
print(result.book.title)
```

`Book.title` and `BookstoreSchema.book.title` are equivalent -- use whichever
reads better in context.

**Multiple root fields:**

```python
result = client.query(
    BookstoreSchema[
        BookstoreSchema.book(id=42)[Book.title, Book.isbn],
        BookstoreSchema.genres,  # auto-selects all scalar sub-fields
    ],
)
```

**Aliases:**

```python
# Top-level alias via keyword argument:
result = client.query(
    BookstoreSchema(
        favourite=BookstoreSchema.book(id=42)[Book.title],
    ),
)
print(result.favourite.title)

# Nested alias via .as_():
result = client.query(
    BookstoreSchema[
        BookstoreSchema.book(id=42)[
            Book.title,
            Book.reviews.as_("recent_reviews")[
                Review.rating,
                Review.text,
            ],
        ],
    ],
)
print(result.book.recent_reviews)
```

**Query variables:**

```python
result = client.query(
    BookstoreSchema[
        BookstoreSchema.book(id=Variable.book_id)[
            Book.title,
            Book.author[Author.name],
        ],
    ],
    variables={"book_id": 42},
)
```

Variable types are automatically inferred from the schema and included in the
generated query string (e.g. `query($book_id: ID!) { ... }`).

**Raw GraphQL strings** are still supported:

```python
result = client.query(
    '{ book(id: 42) { title author { name } } }',
)
```

### Tab Completion

In Jupyter notebooks and IPython, pressing `<Tab>` after `BookstoreSchema.` or
`BookstoreSchema.book.` lists all available fields. `dir()` on any
`FieldSelector` returns its child fields.

### Argument Validation

Fields that accept arguments have those arguments defined in the schema. If
you pass an unknown argument, a `TypeError` is raised immediately:

```python
BookstoreSchema.book(bad_arg=1)
# TypeError: Unknown argument 'bad_arg' for field 'book'. Valid arguments: id
```

Fields that take no arguments raise `TypeError` if called:

```python
Book.title(x=1)
# TypeError: Field 'title' takes no arguments
```

### Auto-expansion of Scalar Fields

When a composite-type field is used without explicit sub-field selections, all
of its scalar fields are automatically included:

```python
BookstoreSchema.genres
# Equivalent to:
BookstoreSchema.genres[Genre.id, Genre.name, Genre.description]
```

## Response Objects

Query results are wrapped in `GraphQLResponse` objects that provide typed
attribute access. Field names are automatically converted to `snake_case`.

```python
result = client.query(
    BookstoreSchema[
        BookstoreSchema.book(id=42)[
            Book.title,
            Book.page_count,
            Book.author[Author.id, Author.name],
        ],
    ],
)

result.book.title        # str
result.book.page_count   # int
result.book.author       # GraphQLResponse (typed as Author)
result.book.author.name  # str
```

### Aliases in Responses

Query aliases work naturally. The response attribute uses whatever name
appeared in the query:

```python
result = client.query(
    BookstoreSchema(
        favourite=BookstoreSchema.book(id=42)[Book.title],
    ),
)
result.favourite.title  # works
```

### Repr

Response objects display with their schema type name and loaded fields:

```python
>>> result.book
Book(title='The Great Gatsby', page_count=180, author=Author(id=7, name='F. Scott Fitzgerald'))
```

Long reprs automatically wrap with indentation at 80 characters.

### Serialization

```python
result.book.to_dict()   # -> {"title": "The Great Gatsby", "pageCount": 180, ...}
result.book.to_json()   # -> '{"title": "The Great Gatsby", "pageCount": 180, ...}'
```

## Lazy Loading

If `auto_fetch` is enabled (the default), accessing a field that was not
included in the original query triggers an automatic re-query:

```python
result = client.query(
    BookstoreSchema[
        BookstoreSchema.book(id=42)[Book.title],
    ],
)

# 'author' was not in the query, but accessing it triggers a lazy fetch:
result.book.author  # automatically re-queries the server
```

The lazy loader:
1. Finds the field's type from the schema metadata
2. Determines which scalar sub-fields to request
3. Modifies the original query to include the missing field
4. Re-executes the query and extracts the new data
5. Caches the result for subsequent access

Disable with `auto_fetch=False`:

```python
client = BookstoreClient("...", auto_fetch=False)
```

Accessing an unloaded field then raises `FieldNotLoadedError`.

## Mutations

```python
result = client.mutate(
    'mutation { addBook(input: { title: "New Book" }) { id title } }',
)
```

## Generated Package Structure

```
bookstore/                   # Project root (dist name, hyphens)
  bookstore/                 # Python module (import name, underscores)
    __init__.py              # Exports client, schema, models, Variable
    client.py                # BookstoreClient class
    models.py                # Schema types, TYPE_REGISTRY, BookstoreSchema
    enums.py                 # Python Enum classes
    inputs.py                # @dataclass input types with to_dict()
    _runtime/                # Standalone runtime library
      builder.py             # Query builder (Variable, FieldSelector, SchemaField)
      model.py               # GraphQLResponse, lazy loading
      client.py              # GraphQLClientBase, HTTP transport
      query.py               # __typename insertion, query modification
      serialization.py       # Case conversion, input serialization
  pyproject.toml             # Package metadata
```

With `--module` the `pyproject.toml` is omitted and the source files are written
directly into `bookstore/` (no nesting), ready to drop into an existing package.

## Schema Support

| GraphQL Feature | Python Representation |
|----------------|----------------------|
| Object types | `GraphQLModel` subclass with `SchemaField` descriptors |
| Interfaces | Base class; implementing types inherit from it |
| Unions | Type alias (`A \| B \| C`) |
| Enums | `enum.Enum` subclass |
| Input types | `@dataclass` with `to_dict()` |
| Custom scalars | Mapped to Python types (`DateTime` -> `str`, `JSON` -> `Any`) |
| `@oneOf` inputs | Validated in `__post_init__` (exactly one field set) |
| `__typename` | Automatically inserted into all queries |

## Type Mapping

| GraphQL | Python |
|---------|--------|
| `String` | `str` |
| `Int` | `int` |
| `Float` | `float` |
| `Boolean` | `bool` |
| `ID` | `str` |
| `DateTime` | `str` |
| `JSON` | `Any` |
| `[Type]` | `list[Type]` |
| `Type!` | Non-null |
| `Type` | `Type \| None` |
