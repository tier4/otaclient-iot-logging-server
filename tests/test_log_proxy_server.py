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
import os
import random
from dataclasses import dataclass
from pathlib import Path
from queue import Queue

import grpc
import pytest
from pytest_mock import MockerFixture

import otaclient_iot_logging_server.log_proxy_server as log_server_module
from otaclient_iot_logging_server._common import LogsQueue
from otaclient_iot_logging_server.ecu_info import parse_ecu_info
from otaclient_iot_logging_server.v1 import otaclient_iot_logging_server_v1_pb2 as pb2
from otaclient_iot_logging_server.v1 import (
    otaclient_iot_logging_server_v1_pb2_grpc as v1_grpc,
)
from otaclient_iot_logging_server.v1 import types
from otaclient_iot_logging_server.v1.api_stub import OtaClientIoTLoggingServiceV1
from otaclient_iot_logging_server.v1.servicer import OTAClientIoTLoggingServerServicer

logger = logging.getLogger(__name__)

MODULE = log_server_module.__name__
TEST_DIR = Path(__file__).parent / "data"


@dataclass
class _ServerConfig:
    """Minimum set of server_config needed for this test."""

    LISTEN_ADDRESS: str = "127.0.0.1"
    LISTEN_PORT: int = 8083
    ECU_INFO_YAML: Path = TEST_DIR / "ecu_info.yaml"
    # remember to disable config file monitor
    EXIT_ON_CONFIG_FILE_CHANGED: bool = False


_test_server_cfg = _ServerConfig()


@dataclass
class MessageEntry:
    ecu_id: str
    log_type: types.LogType
    message: str


# see data/ecu_info.yaml
mocked_ECUs_list = ("main", "sub1", "sub2", "sub3")


def generate_random_msgs(
    ecus_list: tuple[str, ...] = mocked_ECUs_list,
    msg_len: int = 16,
    msg_num: int = 4096,
) -> list[MessageEntry]:
    _res: list[MessageEntry] = []
    for _ in range(msg_num):
        _ecu_id, *_ = random.sample(ecus_list, 1)
        _log_type = random.choice(list(types.LogType))
        _message = os.urandom(msg_len).hex()
        _res.append(MessageEntry(_ecu_id, _log_type, _message))
    return _res


class TestLogProxyServer:
    SERVER_URL = f"{_test_server_cfg.LISTEN_ADDRESS}:{_test_server_cfg.LISTEN_PORT}"
    TOTAL_MSG_NUM = 4096

    @pytest.fixture(autouse=True)
    def mock_ecu_info(self, mocker: MockerFixture):
        self._ecu_info = parse_ecu_info(TEST_DIR / "ecu_info.yaml")
        mocker.patch(f"{MODULE}.ecu_info", self._ecu_info)

    @pytest.fixture(autouse=True)
    async def launch_server(self, mocker: MockerFixture, mock_ecu_info):
        mocker.patch(f"{MODULE}.server_cfg", _test_server_cfg)

        queue: LogsQueue = Queue()
        self._queue = queue

        servicer = OTAClientIoTLoggingServerServicer(
            ecu_info=self._ecu_info,
            queue=queue,
        )

        server = grpc.aio.server()
        v1_grpc.add_OtaClientIoTLoggingServiceServicer_to_server(
            servicer=OtaClientIoTLoggingServiceV1(servicer), server=server
        )
        server.add_insecure_port(self.SERVER_URL)
        try:
            await server.start()
            yield
        finally:
            await server.stop(None)

    @pytest.fixture(autouse=True)
    def prepare_test_data(self):
        self._msgs = generate_random_msgs(msg_num=self.TOTAL_MSG_NUM)

    async def test_server(self):
        # ------ execution ------ #
        logger.info(f"sending {self.TOTAL_MSG_NUM} msgs to {self.SERVER_URL}...")

        async def send_msg(item):
            _req = pb2.PutLogRequest(
                ecu_id=item.ecu_id,
                log_type=item.log_type,
                message=item.message,
            )
            async with grpc.aio.insecure_channel(self.SERVER_URL) as channel:
                stub = v1_grpc.OtaClientIoTLoggingServiceStub(channel)
                _response = await stub.PutLog(_req)
                assert _response.code == pb2.ErrorCode.NO_FAILURE

        for item in self._msgs:
            await send_msg(item)

        # ------ check result ------ #
        # ensure the all msgs are sent in order to the queue by the server.
        logger.info("checking all the received messages...")
        for item in self._msgs:
            _ecu_id, _log_msg = self._queue.get_nowait()
            assert _ecu_id == item.ecu_id
            assert _log_msg["message"] == item.message
        assert self._queue.empty()

    async def test_reject_invalid_ecu_id(self):
        _req = pb2.PutLogRequest(
            ecu_id="bad_ecu_id",
            message="valid_msg",
        )
        async with grpc.aio.insecure_channel(self.SERVER_URL) as channel:
            stub = v1_grpc.OtaClientIoTLoggingServiceStub(channel)
            _response = await stub.PutLog(_req)
            assert _response.code == pb2.ErrorCode.NOT_ALLOWED_ECU_ID

    async def test_reject_invalid_message(self):
        _req = pb2.PutLogRequest(
            ecu_id="main",
            message="",
        )
        async with grpc.aio.insecure_channel(self.SERVER_URL) as channel:
            stub = v1_grpc.OtaClientIoTLoggingServiceStub(channel)
            _response = await stub.PutLog(_req)
            assert _response.code == pb2.ErrorCode.NO_MESSAGE
