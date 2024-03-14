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

import logging
import os
import random
import time
from collections import defaultdict
from datetime import datetime
from queue import Queue
from uuid import uuid1

import pytest
from pytest_mock import MockerFixture

import otaclient_iot_logging_server.aws_iot_logger
from otaclient_iot_logging_server._common import LogMessage, LogsQueue
from otaclient_iot_logging_server.aws_iot_logger import (
    get_log_stream_name,
    AWSIoTLogger,
)

logger = logging.getLogger(__name__)

MODULE = otaclient_iot_logging_server.aws_iot_logger.__name__

_UNIX_EPOCH = datetime(1970, 1, 1, 0, 0)
_UNIX_EPOCH_FMT = "1970/01/01"


@pytest.mark.parametrize(
    "_thing_name, _suffix, _expected",
    [
        (
            "some_thingname",
            "some_suffix",
            f"{_UNIX_EPOCH_FMT}/some_thingname/some_suffix",
        ),
        (
            _thing_name := f"profile-dev-edge-{uuid1()}-Core",
            _suffix := "some_ecu",
            f"{_UNIX_EPOCH_FMT}/{_thing_name}/{_suffix}",
        ),
    ],
)
def test_get_log_stream_name(
    _thing_name: str, _suffix: str, _expected: str, mocker: MockerFixture
):
    _datetime_mock = mocker.MagicMock(spec=datetime)
    _datetime_mock.utcnow.return_value = _UNIX_EPOCH
    mocker.patch(f"{MODULE}.datetime", _datetime_mock)
    assert get_log_stream_name(_thing_name, _suffix) == _expected


_mocked_ECUs_list = ("main_ecu", "sub_ecu0", "sub_ecu1", "sub_ecu2", "sub_ecu3")


def generate_random_msgs(
    msg_len: int,
    msg_num: int,
    ecus_list: tuple[str, ...] = _mocked_ECUs_list,
) -> list[tuple[str, LogMessage]]:
    _res: list[tuple[str, LogMessage]] = []
    for _ in range(msg_num):
        _ecu, *_ = random.sample(ecus_list, 1)
        _msg = os.urandom(msg_len).hex()
        _timestamp = int(time.time()) * 1000  # milliseconds
        _res.append((_ecu, LogMessage(timestamp=_timestamp, message=_msg)))
    return _res


class TestAWSIoTLogger_thread_main:
    MSG_LEN = 16
    MSG_NUM = 4096

    class _TestFinished(Exception):
        pass

    def _mocked_send_messages(self, _ecu_id: str, _logs: list[LogMessage]):
        self._test_result[_ecu_id] = _logs

    @pytest.fixture
    def prepare_test_data(self):
        _msgs = generate_random_msgs(self.MSG_LEN, self.MSG_NUM)

        # prepare result for test_thread_main
        _merged_msgs: dict[str, list[LogMessage]] = defaultdict(list)
        for _ecu_id, _log_msg in _msgs:
            _merged_msgs[_ecu_id].append(_log_msg)
        self._merged_msgs = _merged_msgs

        # prepare the queue for test
        _queue: LogsQueue = Queue()
        for _item in _msgs:
            _queue.put_nowait(_item)
        self._queue = _queue

    @pytest.fixture(autouse=True)
    def setup_test(self, prepare_test_data, mocker: MockerFixture):
        _time_mocker = mocker.MagicMock(spec=time)
        # NOTE: a hack here to interrupt the while loop
        _time_mocker.sleep.side_effect = self._TestFinished
        mocker.patch(f"{MODULE}.time", _time_mocker)

        # ------ prepare test self ------ #
        # The following bound variables will be used in thread_main method.
        # NOTE: another hack to let all entries being merged within one
        #       loop iteration.
        self._max_logs_per_merge = float("inf")
        self.send_messages = self._mocked_send_messages
        self._interval = 6  # place holder
        self._session_config = mocker.MagicMock()  # place holder

        # for holding test results
        # mocked_send_messages will record each calls in this dict
        self._test_result: dict[str, list[LogMessage]] = {}

        # mock get_log_stream_name to let it returns the log_stream_suffix
        # as it, make the test easier.
        # see get_log_stream_name signature for more details
        get_log_stream_name_mock = mocker.MagicMock(wraps=lambda x, y: y)
        mocker.patch(f"{MODULE}.get_log_stream_name", get_log_stream_name_mock)

    def test_thread_main(self, mocker: MockerFixture):
        func_to_test = AWSIoTLogger.thread_main
        self._create_log_group = mocked__create_log_group = mocker.MagicMock(
            spec=AWSIoTLogger._create_log_group
        )

        # ------ execution ------ #
        with pytest.raises(self._TestFinished):
            func_to_test.__get__(self)()
        logger.info("execution finished")

        # ------ check result ------ #
        mocked__create_log_group.assert_called_once()
        # confirm the send_messages mock receives the expecting calls.
        assert self._merged_msgs == self._test_result
