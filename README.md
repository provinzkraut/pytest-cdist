# pytest-cdist

Like pytest-xdist, but for distributed environments.

**This is a work in progress**

## Why?

pytest-xdist can help to parallelize test execution, as long as you can scale
horizontally. In many environments, such as GitHub actions with GitHub runners, this is
only possible to a fairly limited degree, which can be an issue if your test suite grows
large. pytest-cdist can help with this by allowing to execute individual chunks of your
test suite in a deterministic order, so you can use multiple concurrent jobs to run each
individual chunk.

The individual invocation can *still* make use of pytest-xdist.


## How?

```bash
pytest --cdist-group=1/2  # will run the first half of the test suite
pytest --cdist-group=2/2  # will run the second half of the test suite
```

*In a GitHub workflow*

```yaml

jobs:
  test:
    runs-on: ubuntu-latest
    matrix:
      strategy:
        cdist-groups: [1, 2, 3, 4]

    steps:
      - uses: actions/checkout@v4
      # set up environment here
      - name: Run pytest
        run: pytest --cdist-group=${{ matrix.cdist-group }}/4
```

## Usage

### Configuration

Pytest-cdist comes with several CLI and pytest-ini options:

| CLI                     | Ini                   | Allowed values                | Default |
|-------------------------|-----------------------|-------------------------------|---------|
| `--cdist-justify-items` | `cdist-justify-items` | `none`, `file`, `scope`       | `none`  |
| `--cdist-group-steal`   | `--cdist-group-steal` | `<group number>:<percentage>` | -       |
| `--cdist-report`        | -                     | -                             | false   |
| `--cdist-report-dir`    | `cdist-report-dir`    |                               | `.`     |


### Controlling how items are split up

By default, pytest-cdist will split up the items into groups as evenly as possible.
Sometimes this may not be desired, for example if there's some costly fixtures requested
by multiple tests, which should ideally only run once. 

To solve this, the `cdist-justify-items` option can be used to configure how items are
split up. It can take two possible values: 

- `file`: Ensure all items inside a file end up in the same group
- `scope`: Ensure all items in the same pytest scope end up in the same group

```ini
[pytest]
cdist-justify-items=file
```

```bash
pytest --cdist-group=1/2 --cdist-justify-items=file
```


### Skewing the group sizes

Normally, items are distributed evenly among groups, which is a good default, but there
may be cases where this will result in an uneven execution time, if one group contains
a number of slower tests than the other ones. 

To work around this, the `cdist-group-steal` option can be used. It allows to specific 
a certain percentage of items a group will "steal" from other groups. For example 
`--cdist-group-steal=2:30` will cause group `2` to steal 30% of items from all other 
groups.

```ini
[pytest]
cdist-group-steal=2:30
```

```bash
pytest --cdist-group=1/2 --cdist-group-steal=2:30
```

### With pytest-xdist

When running under pytest-xdist, pytest-cdist will honour tests marked with 
`xdist_group`, and group them together in the same cdist group. 


### With pytest-randomly

At the moment, pytest-cdist does not work out of the box with pytest randomly's test
reordering, unless an explicit seed is passed