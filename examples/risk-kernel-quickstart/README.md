# Risk Kernel Quickstart

Run the example from the Sapphire repo root:

```bash
python3 examples/risk-kernel-quickstart/quickstart.py
```

The script builds a fake BTC order, evaluates it through `RiskKernelV1`,
and prints the full verdict tree. A buyer or downstream service can plug in a
custom policy by passing it to the kernel:

```python
from lib.core.risk_kernel import RiskKernelV1, default_policies

kernel = RiskKernelV1(policies=(*default_policies(), MyCustomPolicy()))
verdict = kernel.evaluate(decision)
```

Each policy only needs `name`, `version`, `params`, and
`check(envelope) -> PolicyResult`, so adding one new gate is a one-file change.
