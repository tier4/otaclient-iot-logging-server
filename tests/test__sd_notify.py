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

import socket
from typing import Any

import pytest
import pytest_mock

from otaclient_iot_logging_server import _sd_notify

SD_NOTIFY_MODULE = _sd_notify.__name__


@pytest.fixture
def socket_object_mock(mocker: pytest_mock.MockerFixture):
    return mocker.MagicMock(spec=socket.socket)


@pytest.fixture
def socket_conn_mock(mocker: pytest_mock.MockerFixture, socket_object_mock):
    class DummySocketObject:

        _mock: Any = socket_object_mock

        def __new__(cls, _family, _type, *args):
            cls._family = _family
            cls._type = _type
            return object.__new__(cls)

        def __enter__(self):
            return self._mock

        def __exit__(self, *_):
            return

    mocker.patch(f"{SD_NOTIFY_MODULE}.socket.socket", DummySocketObject)
    yield DummySocketObject


@pytest.mark.parametrize(
    "input, expected",
    (
        (socket_path := "/a/normal/socket/path", socket_path),
        ("@a/abstract/unix/socket", "\0a/abstract/unix/socket"),
    ),
)
def test_get_notify_socket(input, expected, monkeypatch):
    monkeypatch.setenv(_sd_notify.SD_NOTIFY_SOCKET_ENV, input)
    assert _sd_notify.get_notify_socket() == expected


def test_sd_notify(socket_conn_mock, socket_object_mock, monkeypatch):
    NOTIFY_SOCKET = "any_non_empty_value"
    monkeypatch.setenv(_sd_notify.SD_NOTIFY_SOCKET_ENV, NOTIFY_SOCKET)

    # ------ execute ------ #
    _sd_notify.sd_notify(_sd_notify.READY_MSG)

    # ------ check result ------ #
    dummy_socket_class = socket_conn_mock
    assert dummy_socket_class._family == socket.AF_UNIX
    assert dummy_socket_class._type == socket.SOCK_DGRAM

    socket_object_mock.connect.assert_called_once_with(NOTIFY_SOCKET)
    socket_object_mock.sendall.assert_called_once_with(_sd_notify.READY_MSG.encode())
