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
from queue import Queue

import otaclient_iot_logging_server._log_setting
from otaclient_iot_logging_server._log_setting import _LogTeeHandler  # type: ignore
from otaclient_iot_logging_server._common import LogsQueue

MODULE = otaclient_iot_logging_server._log_setting.__name__

logger = logging.getLogger(__name__)


def test_server_logger():
    _queue: LogsQueue = Queue()
    suffix = "test_suffix"

    # ------ setup test ------ #
    _handler = _LogTeeHandler(_queue, suffix)  # type: ignore
    logger.addHandler(_handler)

    # ------ execution ------ #
    logger.info("emit one logging entry")

    # ------ clenaup ------ #
    logger.removeHandler(_handler)

    # ------ check result ------ #
    _log = _queue.get_nowait()
    assert _log[0] == suffix
    assert _log[1]
