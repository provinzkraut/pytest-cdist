from __future__ import annotations

import collections
import dataclasses
import json
import os
import pathlib
import re
from typing import TypeVar, Literal, TYPE_CHECKING

import pytest
from _pytest.stash import StashKey

if TYPE_CHECKING:
    from typing_extensions import TypeAlias

T = TypeVar("T")
JustifyItemsStrategy: TypeAlias = Literal["none", "file", "scope"]

_CDIST_CONFIG_KEY = StashKey["CdistConfig | None"]()


def _partition_list(items: list[T], chunk_size: int) -> list[list[T]]:
    avg_chunk_size = len(items) // chunk_size
    remainder = len(items) % chunk_size

    chunks = []
    start = 0
    for i in range(chunk_size):
        # Distribute remainder items across the first few chunks
        end = start + avg_chunk_size + (1 if i < remainder else 0)
        chunks.append(items[start:end])
        start = end

    return chunks


def _get_item_scope(item: pytest.Item) -> str:
    return item.nodeid.rsplit("::", 1)[0]


def _get_item_file(item: pytest.Item) -> str:
    return item.nodeid.split("::", 1)[0]


@dataclasses.dataclass(frozen=True)
class GroupStealOpt:
    source_group: int | None
    target_group: int
    amount: int

    def __str__(self) -> str:
        out = f"g{self.target_group}:{self.amount}"
        if self.source_group:
            out += f":g{self.source_group}"
        return out


def _distribute(
    groups: list[list[pytest.Item]],
    from_: int,
    to: int,
    amount: int,
) -> None:
    items = groups[from_]
    num_items_to_move = max(0, min(len(items), (len(items) * amount) // 100))
    items_to_move = items[:num_items_to_move]
    groups[to].extend(items_to_move)
    groups[from_] = items[num_items_to_move:]


def _distribute_with_bias(
    groups: list[list[pytest.Item]],
    group_steal: GroupStealOpt,
) -> list[list[pytest.Item]]:
    source_groups = (
        [group_steal.source_group]
        if group_steal.source_group is not None
        else range(len(groups))
    )
    for source_group in source_groups:
        if source_group != group_steal.target_group:
            _distribute(
                groups,
                from_=source_group,
                to=group_steal.target_group,
                amount=group_steal.amount,
            )

    return groups


def _get_group_steal_opt(opt: str | None) -> list[GroupStealOpt]:
    if opt is None:
        return []

    opts = []
    for group_opt in opt.split(","):
        match = re.match(r"g?(\d+):(\d+)(?::g?(\d+))?", group_opt.strip())
        if match is None:
            raise ValueError(f"Invalid group steal option: {group_opt!r}")
        source_group: int | None = None
        target_group = int(match.group(1)) - 1
        amount_to_steal = int(match.group(2))
        if source_group_match := match.group(3):
            source_group = int(source_group_match) - 1

        opts.append(
            GroupStealOpt(
                source_group=source_group,
                target_group=target_group,
                amount=amount_to_steal,
            )
        )
    return opts


def _justify_items(
    groups: list[list[pytest.Item]],
    strategy: Literal["file", "scope"],
) -> list[list[pytest.Item]]:
    get_boundary = _get_item_scope if strategy == "scope" else _get_item_file

    for i, items in enumerate(groups):
        # adjust file grouping
        if not items:
            continue

        last_file = get_boundary(items[-1])
        next_group = groups[i + 1 if i < (len(groups) - 1) else 0]
        if not next_group:
            continue

        next_file = get_boundary(next_group[0])

        if last_file == next_file:
            index = next(
                (i for i, it in enumerate(next_group) if get_boundary(it) != next_file),
                None,
            )

            if index is not None:
                items.extend(next_group[:index])
                next_group[:] = next_group[index:]
            else:
                items.extend(next_group)
                next_group.clear()

    return groups


def _justify_xdist_groups(groups: list[list[pytest.Item]]) -> list[list[pytest.Item]]:
    xdist_groups: dict[str, list[pytest.Item]] = collections.defaultdict(list)

    for i, items in enumerate(groups):
        # find xdist groups
        for item in items[::]:
            for m in item.iter_markers("xdist_group"):
                xdist_groups[m.args[0]].append(item)
                items.remove(item)

    # ensure that we do not break up xdist groups
    for xdist_group, xdist_grouped_items in xdist_groups.items():
        min(groups, key=len).extend(xdist_grouped_items)

    return groups


@dataclasses.dataclass(kw_only=True)
class CdistConfig:
    current_group: int
    total_groups: int
    justify_items_strategy: JustifyItemsStrategy = "none"
    group_steal: list[GroupStealOpt]
    write_report: bool = False
    report_dir: pathlib.Path = pathlib.Path(".")

    def cli_options(self, config: pytest.Config) -> str:
        opts = [f"--cdist-group={self.current_group + 1}/{self.total_groups}"]

        if (
            self.justify_items_strategy != "none"
            and "cdist-justify-items" not in config.inicfg
        ):
            opts.append(f"--cdist-justify-items={self.justify_items_strategy}")

        if self.group_steal and "cdist-group-steal" not in config.inicfg:
            steal_opt = ",".join(map(str, self.group_steal))
            opts.append(f"--cdist-group-steal={steal_opt}")

        if self.write_report:
            opts.append("--cdist-report")

        if (
            self.report_dir != pathlib.Path(".")
            and "cdist-report-dir" not in config.inicfg
        ):
            opts.append(f"--cdist-report-dir={str(self.report_dir)}")

        return " ".join(opts)

    @classmethod
    def from_pytest_config(cls, config: pytest.Config) -> CdistConfig | None:
        cdist_option = config.getoption("cdist_group")

        if cdist_option is None:
            return None

        report_dir = pathlib.Path(
            config.getoption("cdist_report_dir", None)
            or config.getini("cdist-report-dir")
        )

        write_report: bool = config.getoption("cdist_report")

        justify_items_strategy: JustifyItemsStrategy = config.getoption(
            "cdist_justify_items",
            default=None,
        ) or config.getini("cdist-justify-items")

        group_steal = _get_group_steal_opt(
            config.getoption("cdist_group_steal")
            or config.getini("cdist-group-steal")
            or None  # pytest<8 returns an empty string here
        )

        current_group, total_groups = map(int, cdist_option.split("/"))
        if not 0 < current_group <= total_groups:
            raise pytest.UsageError(f"Unknown group {current_group}")

        # using whole numbers (2/2) is more intuitive for the CLI,
        # but here we want to use the group numbers for zero-based indexing
        current_group -= 1

        return cls(
            total_groups=total_groups,
            current_group=current_group,
            report_dir=report_dir,
            write_report=write_report,
            justify_items_strategy=justify_items_strategy,
            group_steal=group_steal,
        )


@pytest.hookimpl
def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("cdist")
    group.addoption("--cdist-group", action="store", default=None)
    group.addoption("--cdist-report", action="store_true", default=False)
    group.addoption("--cdist-report-dir", action="store")
    group.addoption("--cdist-justify-items", action="store")
    group.addoption(
        "--cdist-group-steal",
        action="store",
        default=None,
        help="make a group steal a percentage of items from other groups. '1:30' would "
        "make group 1 steal 30%% of items from all other groups",
    )

    parser.addini("cdist-justify-items", help="justify items strategy", default="none")
    parser.addini(
        "cdist-report-dir", help="cdist report dir", default=".", type="paths"
    )
    parser.addini("cdist-group-steal", help="cdist group steal", default=None)


def pytest_configure(config: pytest.Config) -> None:
    cdist_config = CdistConfig.from_pytest_config(config)
    config.stash[_CDIST_CONFIG_KEY] = cdist_config
    if (
        config.pluginmanager.hasplugin("randomly")
        and config.getoption("randomly_seed") == "default"
        and config.getoption("randomly_reorganize")
    ):
        raise pytest.UsageError(
            "pytest-cdist is incompatible with the current pytest-randomly "
            "configuration and will produce incorrect results. To use both of them "
            "together, either specify a randomness seed using '--randomly-seed=...' or "
            "disable test reorganization by passing '--randomly-dont-reorganize'."
        )


def pytest_collection_modifyitems(
    session: pytest.Session, config: pytest.Config, items: list[pytest.Item]
) -> None:
    cdist_config = config.stash.get(_CDIST_CONFIG_KEY, None)

    if cdist_config is None:
        return

    if cdist_config.total_groups == 1:
        return

    groups = _partition_list(items, cdist_config.total_groups)

    for group_steal in cdist_config.group_steal:
        groups = _distribute_with_bias(
            groups,
            group_steal=group_steal,
        )

    if cdist_config.justify_items_strategy != "none":
        groups = _justify_items(groups, strategy=cdist_config.justify_items_strategy)

    if os.getenv("PYTEST_XDIST_WORKER"):
        groups = _justify_xdist_groups(groups)

    new_items = groups.pop(cdist_config.current_group)
    deselect = [item for group in groups for item in group]

    if cdist_config.write_report:
        cdist_config.report_dir.joinpath(
            f"pytest_cdist_report_{cdist_config.current_group + 1}.json"
        ).write_text(
            json.dumps(
                {
                    "group": cdist_config.current_group + 1,
                    "total_groups": cdist_config.total_groups,
                    "collected": [i.nodeid for i in items],
                    "selected": [i.nodeid for i in new_items],
                }
            )
        )

    # modify in place here, since setting session.items is unreliable, even if pytest
    # docs say that's what you should use
    items[:] = new_items

    if deselect:
        config.hook.pytest_deselected(items=deselect)


def pytest_report_header(config: pytest.Config) -> list[str]:
    cdist_config = config.stash.get(_CDIST_CONFIG_KEY, None)
    if cdist_config is None:
        return []
    return ["cdist options: " + cdist_config.cli_options(config)]
