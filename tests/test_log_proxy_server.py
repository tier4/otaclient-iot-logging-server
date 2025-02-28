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
from http import HTTPStatus
from pathlib import Path
from queue import Queue
from urllib.parse import urljoin

import aiohttp
import aiohttp.client_exceptions
import grpc
import pytest
from aiohttp import web
from pytest_mock import MockerFixture

import otaclient_iot_logging_server.log_proxy_server as log_server_module
from otaclient_iot_logging_server._common import LogGroupType, LogsQueue
from otaclient_iot_logging_server.ecu_info import parse_ecu_info
from otaclient_iot_logging_server.servicer import OTAClientIoTLoggingServerServicer
from otaclient_iot_logging_server.v1 import _types
from otaclient_iot_logging_server.v1 import otaclient_iot_logging_server_v1_pb2 as pb2
from otaclient_iot_logging_server.v1 import (
    otaclient_iot_logging_server_v1_pb2_grpc as v1_grpc,
)
from otaclient_iot_logging_server.v1.api_stub import OTAClientIoTLoggingServiceV1

logger = logging.getLogger(__name__)

MODULE = log_server_module.__name__
TEST_DIR = Path(__file__).parent / "data"


@dataclass
class _ServerConfig:
    """Minimum set of server_config needed for this test."""

    LISTEN_ADDRESS: str = "127.0.0.1"
    LISTEN_PORT: int = 8083
    # In github actions, the port 8084 is already used by mono process.
    LISTEN_PORT_GRPC: int = 8085
    ECU_INFO_YAML: Path = TEST_DIR / "ecu_info.yaml"
    # remember to disable config file monitor
    EXIT_ON_CONFIG_FILE_CHANGED: bool = False


_test_server_cfg = _ServerConfig()


@dataclass
class MessageEntry:
    ecu_id: str
    log_type: _types.LogType
    timestamp: int
    level: _types.LogLevel
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
        _log_type = random.choice(list(_types.LogType))
        _timestamp = random.randint(0, 2**32)
        _level = random.choice(list(_types.LogLevel))
        _message = os.urandom(msg_len).hex()
        _res.append(MessageEntry(_ecu_id, _log_type, _timestamp, _level, _message))
    return _res


class TestLogProxyServer:
    SERVER_URL = (
        f"http://{_test_server_cfg.LISTEN_ADDRESS}:{_test_server_cfg.LISTEN_PORT}/"
    )
    SERVER_URL_GRPC = (
        f"{_test_server_cfg.LISTEN_ADDRESS}:{_test_server_cfg.LISTEN_PORT_GRPC}"
    )
    TOTAL_MSG_NUM = 4096

    @pytest.fixture(autouse=True)
    def mock_ecu_info(self, mocker: MockerFixture):
        self._ecu_info = parse_ecu_info(TEST_DIR / "ecu_info.yaml")
        mocker.patch(f"{MODULE}.ecu_info", self._ecu_info)

    @pytest.mark.asyncio
    @pytest.fixture
    async def launch_http_server(self, mocker: MockerFixture, mock_ecu_info):
        """
        See https://docs.aiohttp.org/en/stable/web_advanced.html#custom-resource-implementation
            for more details.
        """
        mocker.patch(f"{MODULE}.server_cfg", _test_server_cfg)

        queue: LogsQueue = Queue()
        self._queue = queue

        handler = OTAClientIoTLoggingServerServicer(
            ecu_info=self._ecu_info, queue=queue
        )
        app = web.Application()
        # mute the aiohttp server logging
        aiohttp_server_logger = logging.getLogger("aiohttp")
        aiohttp_server_logger.setLevel("ERROR")
        # add handler to the server
        app.add_routes([web.post(r"/{ecu_id}", handler.http_put_log)])
        # star the server
        runner = web.AppRunner(app)
        try:
            await runner.setup()
            site = web.TCPSite(
                runner, _test_server_cfg.LISTEN_ADDRESS, _test_server_cfg.LISTEN_PORT
            )
            await site.start()
            logger.info(f"test log_proxy_server started at {self.SERVER_URL}")
            yield
        finally:
            await runner.cleanup()

    @pytest.mark.asyncio
    @pytest.fixture
    async def http_client_sesion(self):
        client_session = aiohttp.ClientSession(
            raise_for_status=True,
            timeout=aiohttp.ClientTimeout(total=0.2),  # for speedup testing
        )
        try:
            yield client_session
        finally:
            await client_session.close()

    @pytest.mark.asyncio
    @pytest.fixture
    async def launch_grpc_server(self, mocker: MockerFixture, mock_ecu_info):
        mocker.patch(f"{MODULE}.server_cfg", _test_server_cfg)

        queue: LogsQueue = Queue()
        self._queue = queue

        servicer = OTAClientIoTLoggingServerServicer(
            ecu_info=self._ecu_info,
            queue=queue,
        )

        server = grpc.aio.server()
        v1_grpc.add_OTAClientIoTLoggingServiceServicer_to_server(
            servicer=OTAClientIoTLoggingServiceV1(servicer), server=server
        )
        server.add_insecure_port(self.SERVER_URL_GRPC)
        try:
            await server.start()
            yield
        finally:
            await server.stop(None)
            await server.wait_for_termination()

    @pytest.fixture(autouse=True)
    def prepare_test_data(self):
        self._msgs = generate_random_msgs(msg_num=self.TOTAL_MSG_NUM)

    async def test_http_server(
        self,
        launch_http_server,
        http_client_sesion: aiohttp.ClientSession,
    ):
        # ------ execution ------ #
        logger.info(f"sending {self.TOTAL_MSG_NUM} msgs to {self.SERVER_URL}...")
        for item in self._msgs:
            _ecu_id, _msg = item.ecu_id, item.message
            _log_upload_endpoint_url = urljoin(self.SERVER_URL, _ecu_id)
            async with http_client_sesion.post(_log_upload_endpoint_url, data=_msg):
                pass  # raise_for_status is set on session
        # ------ check result ------ #
        # ensure the all msgs are sent in order to the queue by the server.
        logger.info("checking all the received messages...")
        for item in self._msgs:
            _log_group_type, _ecu_id, _log_msg = self._queue.get_nowait()
            # always log type is LOG in HTTP
            assert _log_group_type == LogGroupType.LOG
            assert _ecu_id == item.ecu_id
            assert _log_msg["message"] == item.message
        assert self._queue.empty()

    @pytest.mark.parametrize(
        "_ecu_id, _data",
        [
            # unknowned ECU's request will be dropped
            ("bad_ecu_id", "valid_msg"),
            # empty message will be dropped
            ("main", ""),
        ],
    )
    async def test_http_reject_invalid_request(
        self,
        _ecu_id: str,
        _data: str,
        launch_http_server,
        http_client_sesion: aiohttp.ClientSession,
    ):
        with pytest.raises(aiohttp.client_exceptions.ClientResponseError) as exc_info:
            _log_upload_endpoint_url = urljoin(self.SERVER_URL, _ecu_id)
            async with http_client_sesion.post(_log_upload_endpoint_url, data=_data):
                pass  # raise_for_status is set on session
        assert exc_info.value.status == HTTPStatus.BAD_REQUEST

    @pytest.mark.parametrize(
        "_service",
        ["", "OTAClientIoTLoggingService"],
    )
    async def test_grpc_server_check(self, _service: str, launch_grpc_server):
        _req = pb2.HealthCheckRequest(service=_service)
        async with grpc.aio.insecure_channel(self.SERVER_URL_GRPC) as channel:
            stub = v1_grpc.OTAClientIoTLoggingServiceStub(channel)
            _response = await stub.Check(_req)
            assert _response.status == pb2.HealthCheckResponse.SERVING

    async def test_grpc_server_put_log(self, launch_grpc_server):
        # ------ execution ------ #
        logger.info(f"sending {self.TOTAL_MSG_NUM} msgs to {self.SERVER_URL_GRPC}...")

        async def send_put_log_msg(item):
            _req = pb2.PutLogRequest(
                ecu_id=item.ecu_id,
                log_type=item.log_type,
                timestamp=item.timestamp,
                level=item.level,
                message=item.message,
            )
            async with grpc.aio.insecure_channel(self.SERVER_URL_GRPC) as channel:
                stub = v1_grpc.OTAClientIoTLoggingServiceStub(channel)
                _response = await stub.PutLog(_req)
                assert _response.code == pb2.ErrorCode.NO_FAILURE

        def convert_from_log_type_to_log_group_type(log_type):
            """
            Convert input log type to log group type
            """
            if log_type == _types.LogType.METRICS:
                return LogGroupType.METRICS
            return LogGroupType.LOG

        for item in self._msgs:
            await send_put_log_msg(item)

        # ------ check result ------ #
        # ensure the all msgs are sent in order to the queue by the server.
        logger.info("checking all the received messages...")
        for item in self._msgs:
            _log_group_type, _ecu_id, _log_msg = self._queue.get_nowait()
            assert _ecu_id == item.ecu_id
            assert _log_group_type == convert_from_log_type_to_log_group_type(
                item.log_type
            )
            assert _log_msg["message"] == item.message
        assert self._queue.empty()

    async def test_gprc_reject_invalid_ecu_id(
        self,
        launch_grpc_server,
    ):
        _req = pb2.PutLogRequest(
            ecu_id="bad_ecu_id",
            message="valid_msg",
        )
        async with grpc.aio.insecure_channel(self.SERVER_URL_GRPC) as channel:
            stub = v1_grpc.OTAClientIoTLoggingServiceStub(channel)
            _response = await stub.PutLog(_req)
            assert _response.code == pb2.ErrorCode.NOT_ALLOWED_ECU_ID

    async def test_grpc_reject_invalid_message(self, launch_grpc_server):
        _req = pb2.PutLogRequest(
            ecu_id="main",
            message="",
        )
        async with grpc.aio.insecure_channel(self.SERVER_URL_GRPC) as channel:
            stub = v1_grpc.OTAClientIoTLoggingServiceStub(channel)
            _response = await stub.PutLog(_req)
            assert _response.code == pb2.ErrorCode.NO_MESSAGE
