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
from queue import Full

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

    async def put_log(self, request: PutLogRequest) -> PutLogResponse:
        """
        NOTE: use <ecu_id> as log_stream_suffix, each ECU has its own
              logging stream for uploading.
        """
        _ecu_id = request.ecu_id
        _timestamp = request.timestamp
        _message = request.data
        _allowed_ecus = self._allowed_ecus
        # don't allow empty request or unknowned ECUs
        # if ECU id is unknown(not listed in ecu_info.yaml), drop this log.
        if not _message or (_allowed_ecus and _ecu_id not in _allowed_ecus):
            return PutLogResponse(ErrorCode.NOT_ALLOWED_ECU_ID)

        _logging_msg = LogMessage(
            timestamp=_timestamp * 1000,  # milliseconds
            message=_message,
        )
        # logger.debug(f"receive log from {_ecu_id}: {_logging_msg}")
        try:
            self._queue.put_nowait((_ecu_id, _logging_msg))
        except Full:
            logger.debug(f"message dropped: {_logging_msg}")
            return PutLogResponse(code=ErrorCode.SERVER_ERROR)

        return PutLogResponse(code=ErrorCode.NO_FAILURE)
