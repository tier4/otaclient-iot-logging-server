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
"""Defined wrappers for otaclient_iot_logging_server_v1 protobuf message types."""

from __future__ import annotations

from typing import Optional as _Optional

from otaclient_iot_logging_server.v1 import otaclient_iot_logging_server_v1_pb2 as pb2
from proto_wrapper.proto_wrapper import (
    EnumWrapper,
    MessageWrapper,
    calculate_slots,
)

# enum


class LogType(EnumWrapper):
    LOG = pb2.LOG
    METRICS = pb2.METRICS


class LogLevel(EnumWrapper):
    UNSPECIFIC = pb2.UNSPECIFIC
    TRACE = pb2.TRACE
    DEBUG = pb2.DEBUG
    INFO = pb2.INFO
    WARN = pb2.WARN
    ERROR = pb2.ERROR
    FATAL = pb2.FATAL


class ErrorCode(EnumWrapper):
    NO_FAILURE = pb2.NO_FAILURE
    SERVER_ERROR = pb2.SERVER_ERROR
    NOT_ALLOWED_ECU_ID = pb2.NOT_ALLOWED_ECU_ID


# message wrapper definitions


# PutLog API v1


class PutLogRequest(MessageWrapper[pb2.PutLogRequest]):
    __slots__ = calculate_slots(pb2.PutLogRequest)
    ecu_id: str
    log_type: LogType
    timestamp: int
    level: LogLevel
    message: str

    def __init__(
        self,
        *,
        ecu_id: _Optional[str] = ...,
        log_type: _Optional[LogType] = ...,
        timestamp: _Optional[int] = ...,
        level: _Optional[LogLevel] = ...,
        message: _Optional[str] = ...,
    ) -> None: ...


class PutLogResponse(MessageWrapper[pb2.PutLogResponse]):
    __slots__ = calculate_slots(pb2.PutLogResponse)
    code: ErrorCode
    message: str

    def __init__(
        self,
        *,
        code: _Optional[ErrorCode] = ...,
        message: _Optional[str] = ...,
    ) -> None: ...
