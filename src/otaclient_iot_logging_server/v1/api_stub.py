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

from typing import Any

from otaclient_iot_logging_server.v1 import otaclient_iot_logging_server_v1_pb2 as pb2
from otaclient_iot_logging_server.v1 import (
    otaclient_iot_logging_server_v1_pb2_grpc as pb2_grpc,
)
from otaclient_iot_logging_server.v1 import types


class OtaClientIoTLoggingServiceV1(pb2_grpc.OtaClientIoTLoggingServiceServicer):
    def __init__(self, otaclient_iot_logging_server_stub: Any):
        self._stub = otaclient_iot_logging_server_stub

    async def PutLog(self, request: pb2.PutLogRequest, context) -> pb2.PutLogResponse:
        response = await self._stub.put_log_grpc(types.PutLogRequest.convert(request))
        return response.export_pb()
