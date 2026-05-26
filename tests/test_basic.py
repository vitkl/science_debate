"""Smoke test that the package itself imports and exposes its version."""

import science_debate


def test_package_imports():
    assert hasattr(science_debate, "__version__")
    assert isinstance(science_debate.__version__, str)
