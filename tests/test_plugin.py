from __future__ import annotations

import json

import pytest


def test_split_simple(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("""
    def test_one():
        assert True

    def test_two():
        assert False
    """)

    result = pytester.runpytest("--cdist-group=1/2")
    result.assert_outcomes(passed=1, deselected=1)

    result = pytester.runpytest("--cdist-group=2/2")
    result.assert_outcomes(failed=1, deselected=1)


def test_split_with_preselect(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("""
    def test_one():
        assert True

    def test_two():
        assert False

    def test_three():
        assert True
    """)

    result = pytester.runpytest("--cdist-group=1/2", "-k", "two")
    result.assert_outcomes(failed=1, deselected=2)

    result = pytester.runpytest("--cdist-group=2/2", "-k", "two")
    result.assert_outcomes(passed=0, deselected=3)


def test_justify_file(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("""
    def test_one():
        assert True

    def test_two():
        assert True

    def test_three():
        assert True
    """)

    result = pytester.runpytest("--cdist-group=1/2", "--cdist-justify-items=file")
    result.assert_outcomes(passed=3)
    result = pytester.runpytest("--cdist-group=2/2", "--cdist-justify-items=file")
    result.assert_outcomes(passed=0, deselected=3)


def test_justify_scope(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("""
    class TestSomething:
        def test_one(self):
            assert True

        def test_two(self):
            assert True

    class TestSomethingElse:
        def test_three(self):
            assert True
    """)

    result = pytester.runpytest("--cdist-group=1/2", "--cdist-justify-items=scope")
    result.assert_outcomes(passed=2, deselected=1)
    result = pytester.runpytest("--cdist-group=2/2", "--cdist-justify-items=scope")
    result.assert_outcomes(passed=1, deselected=2)


@pytest.mark.parametrize(
    "cli_opt, ini_opt",
    [
        ("--cdist-justify-items=file", None),
        ("--cdist-justify-items=file", "cdist-justify-items=none"),
        ("", "cdist-justify-items=file"),
    ],
)
def test_justify_cli_ini_cfg(
    pytester: pytest.Pytester,
    cli_opt: str,
    ini_opt: str | None,
    ini_tpl: str,
) -> None:
    pytester.makepyfile("""
    def test_one():
        assert True

    def test_two():
        assert True

    def test_three():
        assert True
    """)
    if ini_opt is not None:
        pytester.makeini(ini_tpl + f"\n{ini_opt}")

    result = pytester.runpytest("--cdist-group=1/2", cli_opt)
    result.assert_outcomes(passed=3)
    result = pytester.runpytest("--cdist-group=2/2", cli_opt)
    result.assert_outcomes(passed=0, deselected=3)


def test_justify_xdist_groups(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("""
    import pytest

    def test_no_group():
        pass

    @pytest.mark.xdist_group("one")
    def test_one():
        assert True

    @pytest.mark.xdist_group("one")
    def test_two():
        assert True

    @pytest.mark.xdist_group("two")
    def test_three():
        assert True
    """)

    result = pytester.runpytest("--cdist-group=1/2", "-n", "2")
    result.assert_outcomes(passed=2)
    result = pytester.runpytest("--cdist-group=2/2", "-n", "2")
    # don't assert "deselect" here since it doesn't work properly with xdist
    result.assert_outcomes(passed=2)


def test_report(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("""
    def test_one():
        assert True

    def test_two():
        assert True
    """)

    result = pytester.runpytest("--cdist-group=1/2", "--cdist-report")
    result.assert_outcomes(passed=1, deselected=1)

    result = pytester.runpytest("--cdist-group=2/2", "--cdist-report")
    result.assert_outcomes(passed=1, deselected=1)

    report_file_1 = pytester.path / "pytest_cdist_report_1.json"
    report_file_2 = pytester.path / "pytest_cdist_report_2.json"

    assert report_file_1.exists()
    assert report_file_2.exists()

    assert json.loads(report_file_1.read_text()) == {
        "group": 1,
        "total_groups": 2,
        "collected": ["test_report.py::test_one", "test_report.py::test_two"],
        "selected": ["test_report.py::test_one"],
    }

    assert json.loads(report_file_2.read_text()) == {
        "group": 2,
        "total_groups": 2,
        "collected": ["test_report.py::test_one", "test_report.py::test_two"],
        "selected": ["test_report.py::test_two"],
    }


@pytest.mark.parametrize(
    "cli_opt, ini_opt",
    [
        ("--cdist-group-steal=2:50", None),
        ("", "cdist-group-steal=2:50"),
        ("--cdist-group-steal=2:50", "cdist-group-steal=2:50"),
    ],
)
def test_steal(
    pytester: pytest.Pytester, cli_opt: str, ini_opt: str | None, ini_tpl: str
) -> None:
    pytester.makepyfile("""
    def test_one():
        assert True

    def test_two():
        assert True

    def test_three():
        assert True

    def test_four():
        assert True
    """)

    if ini_opt is not None:
        pytester.makeini(ini_tpl + f"\n{ini_opt}")

    result = pytester.runpytest("--cdist-group=1/2", cli_opt)
    result.assert_outcomes(passed=1, deselected=3)

    result = pytester.runpytest("--cdist-group=2/2", cli_opt)
    result.assert_outcomes(passed=3, deselected=1)


def test_steal_with_justify(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("""
    class TestFoo:
        def test_one(self):
            assert True

        def test_two(self):
            assert True
    """)

    # Stealing should never break the scope
    result = pytester.runpytest(
        "--cdist-group=1/2",
        "--cdist-justify-items=scope",
        "--cdist-group-steal=2:60",
    )
    result.assert_outcomes(passed=2, deselected=0)

    result = pytester.runpytest(
        "--cdist-group=2/2",
        "--cdist-justify-items=scope",
        "--cdist-group-steal=2:60",
    )
    result.assert_outcomes(passed=0, deselected=2)


def test_raises_for_invalid_randomly_cfg(pytester: pytest.Pytester) -> None:
    pytester.makeini("")

    result = pytester.runpytest("--cdist-group=1/2")
    assert (
        "pytest-cdist is incompatible with the current pytest-randomly configuration"
        in result.stderr.str()
    )


@pytest.mark.parametrize("i", range(10))
def test_randomly_with_seed(pytester: pytest.Pytester, i: int) -> None:
    pytester.makeini('[pytest]\naddopts="-p randomly"')

    pytester.makepyfile("""
    def test_one():
        assert True

    def test_two():
        assert True

    def test_three():
        assert False
    """)

    result = pytester.runpytest_subprocess("--cdist-group=1/2", "--randomly-seed=123")
    result.assert_outcomes(passed=1, failed=1, deselected=1)

    result = pytester.runpytest_subprocess("--cdist-group=2/2", "--randomly-seed=123")
    result.assert_outcomes(passed=1, failed=0, deselected=2)


@pytest.mark.parametrize("i", range(10))
def test_randomly_with_dont_reorganize(pytester: pytest.Pytester, i: int) -> None:
    pytester.makeini('[pytest]\naddopts="-p randomly"')

    pytester.makepyfile("""
    def test_one():
        assert True

    def test_two():
        assert True

    def test_three():
        assert False
    """)

    result = pytester.runpytest_subprocess(
        "--cdist-group=1/2", "--randomly-dont-reorganize"
    )
    result.assert_outcomes(passed=2, failed=0, deselected=1)

    result = pytester.runpytest_subprocess(
        "--cdist-group=2/2", "--randomly-dont-reorganize"
    )
    result.assert_outcomes(passed=0, failed=1, deselected=2)
