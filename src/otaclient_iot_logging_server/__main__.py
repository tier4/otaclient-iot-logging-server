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
import time
from queue import Queue

from otaclient_iot_logging_server import __version__
from otaclient_iot_logging_server import package_name as root_package_name
from otaclient_iot_logging_server._common import LogMessage
from otaclient_iot_logging_server.configs import server_cfg
from otaclient_iot_logging_server.greengrass_config import parse_config
from otaclient_iot_logging_server.log_proxy_server import launch_server


class _LogTeeHandler(logging.Handler):
    """Tee the local loggings to a queue."""

    def __init__(
        self,
        queue: Queue[tuple[str, LogMessage]],
        logstream_suffix: str,
        level: int | str = 0,
    ) -> None:
        super().__init__(level)
        self._queue = queue
        self._logstream_suffix = logstream_suffix

    def emit(self, record) -> None:
        try:
            self._queue.put_nowait(
                (
                    self._logstream_suffix,
                    LogMessage(
                        timestamp=int(time.time()) * 1000,  # milliseconds
                        message=self.format(record),
                    ),
                )
            )
        except Exception:
            pass


def _config_logging(
    queue: Queue,
    *,
    format: str,
    level: str,
    enable_server_log: bool,
    server_logstream_suffix: str,
):
    # NOTE: for the root logger, set to CRITICAL to filter away logs from other
    #       external modules unless reached CRITICAL level.
    logging.basicConfig(level=logging.CRITICAL, format=format, force=True)
    # NOTE: set the <loglevel> to the package root logger
    root_logger = logging.getLogger(root_package_name)
    root_logger.setLevel(level)

    if enable_server_log and server_logstream_suffix:
        _tee_handler = _LogTeeHandler(
            queue=queue,
            logstream_suffix=server_logstream_suffix,
            level=level,
        )
        _fmt = logging.Formatter(fmt=server_cfg.SERVER_LOGGING_LOG_FORMAT)
        _tee_handler.setFormatter(_fmt)

        # attach the log tee handler to the root logger
        root_logger.addHandler(_tee_handler)

    return root_logger


def main():
    queue = Queue(maxsize=server_cfg.MAX_LOGS_BACKLOG)

    root_logger = _config_logging(
        queue,
        format=server_cfg.SERVER_LOGGING_LOG_FORMAT,
        level=server_cfg.SERVER_LOGGING_LEVEL,
        enable_server_log=server_cfg.UPLOAD_LOGGING_SERVER_LOGS,
        server_logstream_suffix=server_cfg.SERVER_LOGSTREAM_SUFFIX,
    )

    launch_server(
        parse_config(),
        queue=queue,
        max_logs_per_merge=server_cfg.MAX_LOGS_PER_MERGE,
        interval=server_cfg.UPLOAD_INTERVAL,
    )

    root_logger.info(
        f"logger server({__version__}) is launched at http://{server_cfg.LISTEN_ADDRESS}:{server_cfg.LISTEN_PORT}"
    )


if __name__ == "__main__":
    main()