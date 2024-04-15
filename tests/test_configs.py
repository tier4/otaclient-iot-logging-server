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

import os
from typing import Any

import pytest
from pytest_mock import MockerFixture

from otaclient_iot_logging_server.configs import (
    ConfigurableLoggingServerConfig,
    load_profile_info,
)

from tests.conftest import TEST_DATA_DPATH

AWS_PROFILE_INFO_FPATH = TEST_DATA_DPATH / "aws_profile_info.yaml"


@pytest.mark.parametrize(
    "_mock_envs, _expected",
    [
        # test#0: check default settings:
        (
            {},
            {
                "GREENGRASS_V1_CONFIG": "/greengrass/config/config.json",
                "GREENGRASS_V2_CONFIG": "/greengrass/v2/init_config/config.yaml",
                "AWS_PROFILE_INFO": "/opt/ota/iot-logger/aws_profile_info.yaml",
                "LISTEN_ADDRESS": "127.0.0.1",
                "LISTEN_PORT": 8083,
                "UPLOAD_LOGGING_SERVER_LOGS": False,
                "SERVER_LOGSTREAM_SUFFIX": "iot_logging_server",
                "SERVER_LOGGING_LEVEL": "INFO",
                "SERVER_LOGGING_LOG_FORMAT": "[%(asctime)s][%(levelname)s]-%(name)s:%(funcName)s:%(lineno)d,%(message)s",
                "MAX_LOGS_BACKLOG": 4096,
                "MAX_LOGS_PER_MERGE": 512,
                "UPLOAD_INTERVAL": 60,
                "ECU_INFO_YAML": "/boot/ota/ecu_info.yaml",
            },
        ),
        # test#1: frequently changed settings
        (
            {
                "LISTEN_ADDRESS": "172.16.1.1",
                "SERVER_LOGGING_LEVEL": "ERROR",
                "UPLOAD_INTERVAL": "30",
            },
            {
                "GREENGRASS_V1_CONFIG": "/greengrass/config/config.json",
                "GREENGRASS_V2_CONFIG": "/greengrass/v2/init_config/config.yaml",
                "AWS_PROFILE_INFO": "/opt/ota/iot-logger/aws_profile_info.yaml",
                "LISTEN_ADDRESS": "172.16.1.1",
                "LISTEN_PORT": 8083,
                "UPLOAD_LOGGING_SERVER_LOGS": False,
                "SERVER_LOGSTREAM_SUFFIX": "iot_logging_server",
                "SERVER_LOGGING_LEVEL": "ERROR",
                "SERVER_LOGGING_LOG_FORMAT": "[%(asctime)s][%(levelname)s]-%(name)s:%(funcName)s:%(lineno)d,%(message)s",
                "MAX_LOGS_BACKLOG": 4096,
                "MAX_LOGS_PER_MERGE": 512,
                "UPLOAD_INTERVAL": 30,
                "ECU_INFO_YAML": "/boot/ota/ecu_info.yaml",
            },
        ),
        # test#2: change everything
        (
            {
                "GREENGRASS_V1_CONFIG": "ggv1_cfg.json",
                "GREENGRASS_V2_CONFIG": "ggv2_cfg.yaml",
                "AWS_PROFILE_INFO": "aws_profile_info.yaml",
                "LISTEN_ADDRESS": "172.16.1.1",
                "LISTEN_PORT": "12345",
                "UPLOAD_LOGGING_SERVER_LOGS": "true",
                "SERVER_LOGSTREAM_SUFFIX": "test_logging_server",
                "SERVER_LOGGING_LEVEL": "DEBUG",
                "SERVER_LOGGING_LOG_FORMAT": "someformat",
                "MAX_LOGS_BACKLOG": "1024",
                "MAX_LOGS_PER_MERGE": "128",
                "UPLOAD_INTERVAL": "10",
                "ECU_INFO_YAML": "/some/where/ecu_info.yaml",
            },
            {
                "GREENGRASS_V1_CONFIG": "ggv1_cfg.json",
                "GREENGRASS_V2_CONFIG": "ggv2_cfg.yaml",
                "AWS_PROFILE_INFO": "aws_profile_info.yaml",
                "LISTEN_ADDRESS": "172.16.1.1",
                "LISTEN_PORT": 12345,
                "UPLOAD_LOGGING_SERVER_LOGS": True,
                "SERVER_LOGSTREAM_SUFFIX": "test_logging_server",
                "SERVER_LOGGING_LEVEL": "DEBUG",
                "SERVER_LOGGING_LOG_FORMAT": "someformat",
                "MAX_LOGS_BACKLOG": 1024,
                "MAX_LOGS_PER_MERGE": 128,
                "UPLOAD_INTERVAL": 10,
                "ECU_INFO_YAML": "/some/where/ecu_info.yaml",
            },
        ),
    ],
)
def test_server_config_loading(
    _mock_envs: dict[str, str],
    _expected: dict[str, Any],
    mocker: MockerFixture,
):
    # patch environmental variables while clearing all already
    mocker.patch.dict(os.environ, _mock_envs, clear=True)

    # NOTE: compare by dict to prevent double import from env vars
    assert _expected == ConfigurableLoggingServerConfig().model_dump()


@pytest.mark.parametrize(
    "_in, _expected",
    [
        (
            str(AWS_PROFILE_INFO_FPATH),
            [
                {
                    "profile_name": "profile-dev",
                    "account_id": "012345678901",
                    "credential_endpoint": "abcdefghijk01.credentials.iot.region.amazonaws.com",
                },
                {
                    "profile_name": "profile-stg",
                    "account_id": "012345678902",
                    "credential_endpoint": "abcdefghijk02.credentials.iot.region.amazonaws.com",
                },
                {
                    "profile_name": "profile-prd",
                    "account_id": "012345678903",
                    "credential_endpoint": "abcdefghijk03.credentials.iot.region.amazonaws.com",
                },
            ],
        ),
    ],
)
def test_load_profile_info(_in: str, _expected: dict[str, Any]):
    assert load_profile_info(_in).model_dump() == _expected
