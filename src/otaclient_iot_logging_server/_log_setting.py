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

import contextlib
import logging
import time

from otaclient_iot_logging_server import package_name as root_package_name
from otaclient_iot_logging_server._common import LogGroupType, LogMessage, LogsQueue
from otaclient_iot_logging_server.configs import server_cfg


class _LogTeeHandler(logging.Handler):
    """Implementation of uploading local server loggings to cloudwatch."""

    def __init__(
        self,
        queue: LogsQueue,
        logstream_suffix: str,
    ) -> None:
        super().__init__()
        self._queue = queue
        self._logstream_suffix = logstream_suffix

    def emit(self, record: logging.LogRecord) -> None:
        with contextlib.suppress(Exception):
            self._queue.put_nowait(
                (
                    LogGroupType.LOG,  # always put into log group
                    self._logstream_suffix,
                    LogMessage(
                        timestamp=int(time.time()) * 1000,  # milliseconds
                        message=self.format(record),
                    ),
                )
            )


def config_logging(
    queue: LogsQueue,
    *,
    log_format: str,
    level: str,
    enable_server_log: bool,
    server_logstream_suffix: str,
):
    # NOTE: for the root logger, set to CRITICAL to filter away logs from other
    #       external modules unless reached CRITICAL level.
    logging.basicConfig(level=logging.CRITICAL, format=log_format, force=True)
    # NOTE: set the <loglevel> to the package root logger
    root_logger = logging.getLogger(root_package_name)
    root_logger.setLevel(level)

    if enable_server_log and server_logstream_suffix:
        _tee_handler = _LogTeeHandler(
            queue=queue,
            logstream_suffix=server_logstream_suffix,
        )
        _fmt = logging.Formatter(fmt=server_cfg.SERVER_LOGGING_LOG_FORMAT)
        _tee_handler.setFormatter(_fmt)

        # attach the log tee handler to the root logger
        root_logger.addHandler(_tee_handler)
        root_logger.info(f"enable server logs upload with {server_logstream_suffix=}")

    return root_logger
