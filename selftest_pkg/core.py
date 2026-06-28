"""Trivial, fully typed module so mypy/type-check has a real target."""


def add(a: int, b: int) -> int:
    return a + b


def greet(name: str) -> str:
    return f"hello {name}"
