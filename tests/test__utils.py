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
import logging
import random
from typing import Any

import pytest

from otaclient_iot_logging_server._utils import (
    NestedDict,
    chain_query,
    retry,
    remove_prefix,
    parse_pkcs11_uri,
)

logger = logging.getLogger(__name__)


@pytest.mark.parametrize(
    "_input, _paths, _expected, _default",
    [
        # test#1: succeeded chain_query
        (
            {"a": {"b": {"c": {"d": "e"}}}},
            ["a", "b", "c", "d"],
            "e",
            None,
        ),
        # test#2: failed chain query with <default> set to "default_value"
        (
            {"a": {"b": {"c": {"d": "e"}}}},
            ["non", "existed", "path"],
            "default_value",
            "default_value",
        ),
    ],
)
def test_chain_query(
    _input: NestedDict,
    _paths: str,
    _expected: Any,
    _default: Any,
):
    _queried = chain_query(_input, *_paths, default=_default)
    assert _queried == _expected


class TestRetry:

    class HandledException(Exception):
        pass

    class UnhandledException(Exception):
        pass

    @staticmethod
    def _func_factory(
        _max_retry: int,
        _return_value: Any,
        exception_to_raise: list[Any] | None = None,
    ):
        # return a func that succeeds in first run
        if exception_to_raise is None:
            return lambda: _return_value

        execution_round = 0
        exception_replay = iter(exception_to_raise)

        def _func():
            nonlocal execution_round, exception_replay
            execution_round += 1
            _exception = next(exception_replay, None)

            if _exception is None:
                if execution_round <= _max_retry + 1:
                    return _return_value
                logger.error("retrier doesn't work!")
                raise ValueError
            logger.info(f"{execution_round=}")
            raise _exception

        return _func

    def test_normal_finished(self):
        """
        Function returns directly without raising any exception.
        """
        return_value = random.randint(10**3, 10**6)
        _res = retry(
            self._func_factory(0, return_value),
            retry_on_exceptions=(self.HandledException,),
        )()
        assert _res == return_value

    def test_successfully_retried(self):
        """
        Function failed for some times, within <max_retry>, but finally succeeded.
        """
        return_value = random.randint(10**3, 10**6)
        max_retries, actual_retries = 8, 7

        _res = retry(
            self._func_factory(
                actual_retries,
                return_value,
                exception_to_raise=[
                    self.HandledException for _ in range(actual_retries)
                ],
            ),
            max_retry=max_retries,
            backoff_factor=0.01,  # for speeding up test
            retry_on_exceptions=(self.HandledException,),
        )()
        assert _res == return_value

    def test_aborted_by_unhandled_exception(self):
        return_value = random.randint(10**3, 10**6)
        max_retries, actual_retries = 8, 7

        with pytest.raises(self.UnhandledException):
            retry(
                self._func_factory(
                    actual_retries,
                    return_value,
                    exception_to_raise=[
                        self.HandledException for _ in range(actual_retries - 1)
                    ]
                    + [self.UnhandledException],
                ),
                max_retry=max_retries,
                backoff_factor=0.01,  # for speeding up test
                retry_on_exceptions=(self.HandledException,),
            )()

    def test_aborted_by_exceeded_max_retries(self):
        return_value = random.randint(10**3, 10**6)
        max_retries, actual_retries = 3, 7

        with pytest.raises(self.HandledException):
            _exceptions = [self.HandledException for _ in range(actual_retries)]
            retry(
                self._func_factory(
                    actual_retries,
                    return_value,
                    exception_to_raise=_exceptions,
                ),
                max_retry=max_retries,
                backoff_factor=0.01,  # for speeding up test
                retry_on_exceptions=(self.HandledException,),
            )()

    def test_retry_session_timecost(self):
        """
        For a retry session with the following configurations:
            1. backoff_factor = 0.1
            2. backoff_max = 1
            3. max_retry = 8
        We should have the time cost sequence as follow:
            0.1, 0.2, 0.4, 0.6, 0.8, 1.0, 1.0, 1.0
        So the retry session should not take more than 6s(5.1s+)
        """
        max_retries, actual_retries = 8, 9
        backoff_factor, backoff_max = 0.1, 1

        # NOTE: add some overhead for function execution
        expected_retry_session_timecost = (
            sum(min(backoff_max, backoff_factor * 2**i) for i in range(max_retries))
            + 0.5
        )

        return_value = random.randint(10**3, 10**6)
        with pytest.raises(self.HandledException):
            _start_time = time.time()
            retry(
                self._func_factory(
                    actual_retries,
                    return_value,
                    exception_to_raise=[
                        self.HandledException for _ in range(actual_retries)
                    ],
                ),
                max_retry=max_retries,
                backoff_factor=backoff_factor,
                backoff_max=backoff_max,
                retry_on_exceptions=(self.HandledException,),
            )()

            time_cost = time.time() - _start_time
            logger.info(f"{time_cost=}")
            assert time_cost <= expected_retry_session_timecost


@pytest.mark.parametrize(
    "_input, _prefix, _expected",
    [
        # test#1: test remove schema from pkcs11 URI
        (
            "pkcs11:token=token;object=object;pin-value=pin-value",
            "pkcs11:",
            "token=token;object=object;pin-value=pin-value",
        ),
        # test#2: test remove schema from file URI
        (
            "file:///path/to/something",
            "file://",
            "/path/to/something",
        ),
        (
            "abcabcabcabcabcabcabcabcabc",
            "abc",
            "abcabcabcabcabcabcabcabc",
        ),
    ],
)
def test_remove_prefix(_input: str, _prefix: str, _expected: str):
    assert remove_prefix(_input, _prefix) == _expected


@pytest.mark.parametrize(
    "_pkcs11_uri, _expected",
    [
        # test#1: TypedDict also accepts unknown keys
        (
            "pkcs11:token=token;object=object;slot-id=1;pin-value=pin-value;type=cert",
            {
                "object": "object",
                "token": "token",
                "pin-value": "pin-value",
                "type": "cert",
                "slot-id": "1",
            },
        ),
        # test#2: minimum pkcs11 sample
        (
            "pkcs11:object=object;type=cert",
            {
                "object": "object",
                "type": "cert",
            },
        ),
    ],
)
def test_parse_pkcs11_uri(_pkcs11_uri: str, _expected: dict[str, Any]):
    assert parse_pkcs11_uri(_pkcs11_uri) == _expected
