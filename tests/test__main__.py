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
from dataclasses import dataclass

import pytest
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

import otaclient_iot_logging_server.__main__ as _main_module

MODULE = _main_module.__name__

logger = logging.getLogger(__name__)


@dataclass
class _ServerCfg:
    """A minimum set of configs used by main module."""

    SERVER_LOGGING_LOG_FORMAT: str = "test_format"
    SERVER_LOGGING_LEVEL: str = "DEBUG"
    UPLOAD_LOGGING_SERVER_LOGS: bool = False
    SERVER_LOGSTREAM_SUFFIX: str = "test_suffix"
    LISTEN_ADDRESS: str = "172.16.1.1"
    LISTEN_PORT: int = 1234
    MAX_LOGS_PER_MERGE: int = 123
    MAX_LOGS_BACKLOG: int = 1234
    UPLOAD_INTERVAL: int = 12


@pytest.mark.parametrize("_in_server_cfg, _version", [(_ServerCfg(), "test_version")])
def test_main(
    _in_server_cfg: _ServerCfg,
    _version: str,
    mocker: MockerFixture,
    caplog: LogCaptureFixture,
):
    # ------ prepare patching ------ #
    mocker.patch(
        f"{MODULE}.config_logging",
        _logger_mock := mocker.MagicMock(return_value=logger),
    )
    mocker.patch(
        f"{MODULE}.start_aws_iot_logger_thread",
        _aws_iot_logger_mock := mocker.MagicMock(),
    )
    mocker.patch(
        f"{MODULE}.launch_server",
        _launch_server_mock := mocker.MagicMock(),
    )
    mocker.patch(f"{MODULE}.__version__", _version)
    mocker.patch(f"{MODULE}.server_cfg", _in_server_cfg)

    # ------ execution ------ #
    _main_module.main()

    # ------ check result ------ #
    _logger_mock.assert_called_once_with(
        mocker.ANY,
        format=_in_server_cfg.SERVER_LOGGING_LOG_FORMAT,
        level=_in_server_cfg.SERVER_LOGGING_LEVEL,
        enable_server_log=_in_server_cfg.UPLOAD_LOGGING_SERVER_LOGS,
        server_logstream_suffix=_in_server_cfg.SERVER_LOGSTREAM_SUFFIX,
    )
    _aws_iot_logger_mock.assert_called_once()
    _launch_server_mock.assert_called_once()

    # check __main__.main source code for more details
    assert (
        caplog.records[-2].msg
        == f"launching iot_logging_server({_version}) at http://{_in_server_cfg.LISTEN_ADDRESS}:{_in_server_cfg.LISTEN_PORT}"
    )
    assert (caplog.records[-1].msg) == f"iot_logging_server config: \n{_in_server_cfg}"
