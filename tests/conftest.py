import pytest

pytest_plugins = ["pytester"]


@pytest.fixture()
def ini_tpl() -> str:
    return '[pytest]\naddopts="-p no:randomly"'


@pytest.fixture(autouse=True)
def make_ini(pytester: pytest.Pytester, ini_tpl: str) -> None:
    pytester.makeini(ini_tpl)
