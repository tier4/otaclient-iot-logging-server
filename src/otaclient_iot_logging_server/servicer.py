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
"""OTA Client IoT Logging Server v1 implementation."""

from __future__ import annotations

import logging
import time
from http import HTTPStatus
from queue import Full

from aiohttp import web
from aiohttp.web import Request

from otaclient_iot_logging_server._common import LogMessage, LogsQueue
from otaclient_iot_logging_server.ecu_info import ECUInfo
from otaclient_iot_logging_server.v1.types import (
    ErrorCode,
    PutLogRequest,
    PutLogResponse,
)

logger = logging.getLogger(__name__)


class OTAClientIoTLoggingServerServicer:
    """Handlers for otaclient IoT logging service."""

    def __init__(
        self,
        *,
        ecu_info: ECUInfo,
        queue: LogsQueue,
    ):
        self._queue = queue
        self._allowed_ecus = None

        if ecu_info:
            self._allowed_ecus = ecu_info.ecu_id_set
            logger.info(
                f"setup allowed_ecu_id from ecu_info.yaml: {ecu_info.ecu_id_set}"
            )
        else:
            logger.warning(
                "no ecu_info.yaml presented, logging upload filtering is DISABLED"
            )

    async def put_log(self, ecu_id, message):
        """
        Put log message into queue.

        """
        # don't allow empty message request
        if not message:
            return ErrorCode.NO_MESSAGE
        # don't allow unknowned ECUs
        # if ECU id is unknown(not listed in ecu_info.yaml), drop this log.
        if self._allowed_ecus and ecu_id not in self._allowed_ecus:
            return ErrorCode.NOT_ALLOWED_ECU_ID

        _timestamp = (int(time.time()) * 1000,)  # milliseconds
        _logging_msg = LogMessage(
            timestamp=_timestamp,
            message=message,
        )
        # logger.debug(f"receive log from {ecu_id}: {_logging_msg}")
        try:
            self._queue.put_nowait((ecu_id, _logging_msg))
        except Full:
            logger.debug(f"message dropped: {_logging_msg}")
            return ErrorCode.SERVER_QUEUE_FULL

        return ErrorCode.NO_FAILURE

    async def put_log_http(self, request: Request) -> PutLogResponse:
        """
        put log message from HTTP POST request.
        """
        _ecu_id = request.match_info["ecu_id"]
        _message = await request.text()

        _code = await self.put_log(_ecu_id, _message)

        if _code == ErrorCode.NO_MESSAGE or _code == ErrorCode.NOT_ALLOWED_ECU_ID:
            _status = HTTPStatus.BAD_REQUEST
        elif _code == ErrorCode.SERVER_QUEUE_FULL:
            _status = HTTPStatus.SERVICE_UNAVAILABLE
        else:
            _status = HTTPStatus.OK

        return web.Response(status=_status)

    async def put_log_grpc(self, request: PutLogRequest) -> PutLogResponse:
        """
        put log message from gRPC request
        """
        _ecu_id = request.ecu_id
        _message = request.message

        _code = await self.put_log(_ecu_id, _message)
        return PutLogResponse(code=_code)
