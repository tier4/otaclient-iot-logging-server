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

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

import grpc.aio

from otaclient_iot_logging_server._common import LogsQueue
from otaclient_iot_logging_server._sd_notify import (
    READY_MSG,
    sd_notify,
    sd_notify_enabled,
)
from otaclient_iot_logging_server.configs import server_cfg
from otaclient_iot_logging_server.ecu_info import ecu_info
from otaclient_iot_logging_server.v1 import (
    otaclient_iot_logging_server_v1_pb2_grpc as v1_grpc,
)
from otaclient_iot_logging_server.v1.api_stub import OtaClientIoTLoggingServiceV1
from otaclient_iot_logging_server.v1.servicer import OTAClientIoTLoggingServerServicer

logger = logging.getLogger(__name__)


WAIT_BEFORE_SEND_READY_MSG = 2  # seconds


def launch_server(queue: LogsQueue) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    if sd_notify_enabled():
        logger.info(
            "otaclient-logger service is configured to send ready msg to systemd, "
            f"wait for {WAIT_BEFORE_SEND_READY_MSG} seconds for the server starting up ..."
        )

        loop.call_later(
            WAIT_BEFORE_SEND_READY_MSG,
            sd_notify,
            READY_MSG,
        )

    async def _grpc_server_launcher():
        thread_pool = ThreadPoolExecutor(
            thread_name_prefix="otaclient_iot_logging_server",
        )
        servicer = OTAClientIoTLoggingServerServicer(
            ecu_info=ecu_info,
            queue=queue,
        )
        otaclient_iot_logging_service_v1 = OtaClientIoTLoggingServiceV1(servicer)

        server = grpc.aio.server(thread_name_prefix=thread_pool)
        v1_grpc.add_OtaClientIoTLoggingServiceServicer_to_server(
            server=server, servicer=otaclient_iot_logging_service_v1
        )
        server.add_insecure_port(
            f"{server_cfg.LISTEN_ADDRESS}:{server_cfg.LISTEN_PORT}"
        )
        logger.info(
            f"launch grpc server at {server_cfg.LISTEN_ADDRESS}:{server_cfg.LISTEN_PORT}"
        )

        await server.start()
        try:
            await server.wait_for_termination()
        finally:
            await server.stop(1)
            thread_pool.shutdown(wait=True)

    loop.create_task(_grpc_server_launcher())
    loop.run_forever()
