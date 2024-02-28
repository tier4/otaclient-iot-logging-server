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

from queue import Queue

from otaclient_iot_logging_server import __version__
from otaclient_iot_logging_server._common import LogsQueue
from otaclient_iot_logging_server._log_setting import config_logging
from otaclient_iot_logging_server.aws_iot_logger import start_aws_iot_logger_thread
from otaclient_iot_logging_server.configs import server_cfg
from otaclient_iot_logging_server.log_proxy_server import launch_server


def main() -> None:
    # server scope log entries pipe
    queue: LogsQueue = Queue(maxsize=server_cfg.MAX_LOGS_BACKLOG)

    # ------ configure local logging ------ #
    root_logger = config_logging(
        queue,
        format=server_cfg.SERVER_LOGGING_LOG_FORMAT,
        level=server_cfg.SERVER_LOGGING_LEVEL,
        enable_server_log=server_cfg.UPLOAD_LOGGING_SERVER_LOGS,
        server_logstream_suffix=server_cfg.SERVER_LOGSTREAM_SUFFIX,
    )

    # ------ start server ------ #
    root_logger.info(
        f"launching iot_logging_server({__version__}) at http://{server_cfg.LISTEN_ADDRESS}:{server_cfg.LISTEN_PORT}"
    )
    root_logger.info(f"iot_logging_server config: \n{server_cfg}")

    start_aws_iot_logger_thread(queue)
    launch_server(queue=queue)  # NoReturn


if __name__ == "__main__":
    main()
