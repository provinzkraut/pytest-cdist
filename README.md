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
