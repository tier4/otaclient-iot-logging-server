# Copyright 2022 TIER IV, INC. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from __future__ import annotations

import time
from functools import partial, wraps
from typing import Any, Callable, Optional, TypeVar, overload

from pydantic import BaseModel, ConfigDict
from typing_extensions import ParamSpec, TypeAlias

from otaclient_iot_logging_server._common import PKCS11URI

RT = TypeVar("RT")
P = ParamSpec("P")
NestedDict: TypeAlias = "dict[str, Any | 'NestedDict']"


class FixedConfig(BaseModel):
    model_config = ConfigDict(frozen=True)


_MISSING = object()


def chain_query(_obj: NestedDict, *_paths: str, default: object = _MISSING) -> Any:
    """Chain access a nested dict <_obj> according to search <_paths>.

    For example:
        for <_obj> as a dict object like the following:
        _obj = {
            "level_name": "root_level",
            "level1": {
                "level_name": "level1,
                "level2": {
                    "level_name": "level2",
                    "attr_we_need": "some_value",
                }
            }
        }

        To get the <attr_we_need>, we can use chain_query func as follow:
            chain_query(_obj, "level1", "level2", "attr_we_need")

    Args:
        _obj: a nested dict object.
        _paths: a list of paths.
        default: if given, returned when chain_query failed.

    Raises:
        ValueError on failed query.
    """
    try:
        for _next in _paths:
            _obj = _obj[_next]
        return _obj
    except Exception as e:
        if default is not _MISSING:
            return default
        raise ValueError(f"chain query with {_paths=} failed: {e!r}") from e


@overload
def retry(
    func: None = None,
    /,
    backoff_factor: float = 0.1,
    backoff_max: int = 6,
    max_retry: int = 6,
    retry_on_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> partial[Any]: ...


@overload
def retry(
    func: Callable[P, RT],
    /,
    backoff_factor: float = ...,
    backoff_max: int = ...,
    max_retry: int = ...,
    retry_on_exceptions: tuple[type[Exception], ...] = ...,
) -> Callable[P, RT]: ...


def retry(
    func: Optional[Callable[P, RT]] = None,
    /,
    backoff_factor: float = 0.1,
    backoff_max: int = 6,
    max_retry: int = 6,
    retry_on_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> partial[Any] | Callable[P, RT]:
    if func is None:
        return partial(
            retry,
            backoff_factor=backoff_factor,
            backoff_max=backoff_max,
            max_retry=max_retry,
            retry_on_exceptions=retry_on_exceptions,
        )

    @wraps(func)
    def _inner(*args: P.args, **kwargs: P.kwargs) -> RT:
        _retry_count = 0
        while True:
            try:
                return func(*args, **kwargs)
            except retry_on_exceptions:
                if max_retry <= 0 or _retry_count < max_retry:
                    _sleeptime = min(backoff_factor * (2**_retry_count), backoff_max)
                    time.sleep(_sleeptime)

                    _retry_count += 1
                    continue
                raise

    return _inner


def remove_prefix(_str: str, _prefix: str) -> str:
    # NOTE: in py3.8 we don't have str.removeprefix yet.
    if _str.startswith(_prefix):
        return _str.replace(_prefix, "", 1)
    return _str


def parse_pkcs11_uri(_pkcs11_uri: str) -> PKCS11URI:
    _, pkcs11_opts_str = _pkcs11_uri.split(":", maxsplit=1)
    pkcs11_opts_dict: dict[str, Any] = {}
    for opt in pkcs11_opts_str.split(";"):
        k, v = opt.split("=", maxsplit=1)
        pkcs11_opts_dict[k] = v
    return PKCS11URI(**pkcs11_opts_dict)
