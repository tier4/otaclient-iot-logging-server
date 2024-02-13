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

from otaclient_iot_logging_server import __version__
from otaclient_iot_logging_server import package_name as root_package_name
from otaclient_iot_logging_server.configs import server_cfg
from otaclient_iot_logging_server.greengrass_config import parse_config
from otaclient_iot_logging_server.log_proxy_server import launch_server


def main():
    # ------ configure the root logger ------ #
    # NOTE: for the root logger, set to CRITICAL to filter away logs from other
    #       external modules unless reached CRITICAL level.
    logging.basicConfig(
        level=logging.CRITICAL, format=server_cfg.SERVER_LOGGING_LOG_FORMAT, force=True
    )
    # NOTE: set the <loglevel> to the package root logger
    root_logger = logging.getLogger(root_package_name)
    root_logger.setLevel(server_cfg.SERVER_LOGGING_LEVEL)
    # ------ launch server ------ #
    launch_server(
        parse_config(),
        max_logs_backlog=server_cfg.MAX_LOGS_BACKLOG,
        max_logs_per_merge=server_cfg.MAX_LOGS_PER_MERGE,
        interval=server_cfg.UPLOAD_INTERVAL,
    )

    root_logger.info(
        f"logger server({__version__}) is launched at http://{server_cfg.LISTEN_ADDRESS}:{server_cfg.LISTEN_PORT}"
    )


if __name__ == "__main__":
    main()
