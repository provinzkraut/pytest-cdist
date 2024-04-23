from typing import TypeVar

import pytest

T = TypeVar("T")


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


def pytest_collection_modifyitems(
    session: pytest.Session, config: pytest.Config, items: list[pytest.Item]
) -> None:
    cdist_option = config.getoption("cdist_group")
    if cdist_option is None:
        return

    current_group, total_groups = map(int, cdist_option.split("/"))
    if not 0 < current_group <= total_groups:
        raise pytest.UsageError(f"Unknown group {current_group}")

    # using whole numbers (2/2) is more intuitive for the CLI,
    # but here we want to use the group numbers for zero-based indexing
    current_group -= 1

    groups = _partition_list(items, total_groups)
    new_items = groups.pop(current_group)
    deselect = [item for group in groups for item in group]

    # modify in place here, since setting session.items is unreliable, even if pytest
    # docs say that's what you should use
    items[:] = new_items

    if deselect:
        config.hook.pytest_deselected(items=deselect)
