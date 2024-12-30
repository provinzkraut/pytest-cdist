from __future__ import annotations

import pytest
from pytest_cdist.check import check


def test_check_group_diff(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("""
    def test_one():
        assert True

    def test_two():
        assert True
    """)

    pytester.runpytest("--cdist-group=1/2", "--cdist-report")
    pytester.runpytest("--cdist-group=2/3", "--cdist-report")

    result = check(pytester.path)
    assert result == ["Different amount of groups specified between runs: 2, 3"]


def test_check_collection_diff(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
    def test_one():
        assert True
    """
    )

    pytester.runpytest("--cdist-group=1/2", "--cdist-report")
    pytester.path.joinpath("test_check_collection_diff.py").unlink()
    pytester.runpytest("--cdist-group=2/2", "--cdist-report")

    result = check(pytester.path)
    assert result == ["Collected different items between runs"]
