from __future__ import annotations
import collections
import json
import pathlib
from typing import TypeVar, Literal

import pytest

T = TypeVar("T")


@pytest.hookimpl
def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("cdist")
    group.addoption("--cdist-group", action="store", default=None)
    group.addoption("--cdist-report", action="store_true", default=False)
    group.addoption(
        "--cdist-report-dir", action="store", default=".", type=pathlib.Path
    )
    group.addoption("--cdist-justify-items", action="store", default="none")
    group.addoption(
        "--cdist-group-steal",
        action="store",
        default=None,
        help="make a group steal a percentage of items from other groups. '1:30' would "
        "make group 1 steal 30 % of items from all other groups)",
    )


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


def _distribute_with_bias(
    groups: list[list[pytest.Item]], target: int, bias: int
) -> list[list[pytest.Item]]:
    for i, lst in enumerate(groups):
        if i != target:
            num_items_to_move = max(0, min(len(lst), (len(lst) * bias) // 100))
            items_to_move = lst[:num_items_to_move]
            groups[target].extend(items_to_move)
            groups[i] = lst[num_items_to_move:]

    return groups


def _get_group_steal_opt(opt: str | None) -> tuple[int, int] | None:
    if opt is None:
        return None
    target_group, amount_to_steal = opt.split(":")
    return int(target_group) - 1, int(amount_to_steal)


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


def pytest_collection_modifyitems(
    session: pytest.Session, config: pytest.Config, items: list[pytest.Item]
) -> None:
    cdist_option = config.getoption("cdist_group")

    if cdist_option is None:
        return

    report_dir: pathlib.Path = config.getoption("cdist_report_dir")
    write_report: bool = config.getoption("cdist_report")
    justify_items_strategy: Literal["none", "file", "scope"] = config.getoption(
        "cdist_justify_items"
    )
    group_steal = _get_group_steal_opt(config.getoption("cdist_group_steal"))

    current_group, total_groups = map(int, cdist_option.split("/"))
    if not 0 < current_group <= total_groups:
        raise pytest.UsageError(f"Unknown group {current_group}")

    # using whole numbers (2/2) is more intuitive for the CLI,
    # but here we want to use the group numbers for zero-based indexing
    current_group -= 1

    groups = _partition_list(items, total_groups)
    if justify_items_strategy != "none":
        groups = _justify_items(groups, strategy=justify_items_strategy)

    # if os.getenv("PYTEST_XDIST_WORKER"):
    groups = _justify_xdist_groups(groups)

    if group_steal is not None:
        target_group, amount_to_steal = group_steal
        groups = _distribute_with_bias(
            groups,
            target=target_group,
            bias=amount_to_steal,
        )

    new_items = groups.pop(current_group)
    deselect = [item for group in groups for item in group]

    if write_report:
        report_dir.joinpath(f"pytest_cdist_report_{current_group + 1}.json").write_text(
            json.dumps(
                {
                    "group": current_group + 1,
                    "total_groups": total_groups,
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
