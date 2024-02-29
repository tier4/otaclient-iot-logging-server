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
from http import HTTPStatus
from queue import Full, Queue

from aiohttp import web
from aiohttp.web import Request

from otaclient_iot_logging_server._common import LogMessage, LogsQueue
from otaclient_iot_logging_server.configs import server_cfg

logger = logging.getLogger(__name__)


class LoggingPostHandler:
    """A simple aiohttp server handler that receives logs from otaclient."""

    def __init__(self, queue: LogsQueue) -> None:
        self._queue = queue

    # route: POST /{ecu_id}
    async def logging_post_handler(self, request: Request):
        """
        NOTE: use <ecu_id> as log_stream_suffix, each ECU has its own
              logging stream for uploading.
        """
        _ecu_id = request.match_info["ecu_id"]
        _raw_logging = await request.text()
        # don't allow empty request or unknowned ECUs
        if not _raw_logging or _ecu_id not in server_cfg.ALLOWED_ECUS:
            return web.Response(status=HTTPStatus.BAD_REQUEST)

        _logging_msg = LogMessage(
            timestamp=int(time.time()) * 1000,  # milliseconds
            message=_raw_logging,
        )
        # logger.debug(f"receive log from {_ecu_id}: {_logging_msg}")

        try:
            self._queue.put_nowait((_ecu_id, _logging_msg))
        except Full:
            logger.debug(f"message dropped: {_logging_msg}")
            return web.Response(status=HTTPStatus.SERVICE_UNAVAILABLE)

        return web.Response(status=HTTPStatus.OK)


def launch_server(queue: Queue[tuple[str, LogMessage]]) -> None:
    handler = LoggingPostHandler(queue=queue)
    app = web.Application()
    app.add_routes([web.post(r"/{ecu_id}", handler.logging_post_handler)])

    # typing: run_app is a NoReturn method, unless received signal
    web.run_app(app, host=server_cfg.LISTEN_ADDRESS, port=server_cfg.LISTEN_PORT)  # type: ignore
