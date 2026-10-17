"""Isolated payload only. Derived from fixed IDM utils.py under Apache-2.0.

Source: bernardo-torres/inverse-drum-machine@456656868538205ef756912c7cf5b0fd936de8af.
Retains exp_sigmoid's exact float32 operations, with only the three activations
used by the selected encoder profile. Upstream Apache notice accompanies payload.
"""

import functools
from typing import Any

import torch  # type: ignore[import-not-found]
from torch import nn


def exp_sigmoid(
    x: Any, exponent: float = 10.0, max_value: float = 2.0, threshold: float = 1e-7
) -> Any:
    x = x.type(torch.float32)
    exponent_tensor = torch.tensor(exponent, dtype=torch.float32, device=x.device)
    return max_value * torch.sigmoid(x) ** torch.log(exponent_tensor) + threshold


def get_act_module(name: str) -> Any:
    if name != "relu":
        raise ValueError("Only the fixed relu activation is allowed")
    return nn.ReLU


def get_act_functional(name: str) -> Any:
    if name == "none":
        return lambda x: x
    if name == "exp_sigmoid":
        return functools.partial(exp_sigmoid, exponent=10.0, max_value=2, threshold=1e-7)
    raise ValueError("Only fixed onset/velocity activations are allowed")
