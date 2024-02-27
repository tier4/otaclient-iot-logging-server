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
import uuid
from dataclasses import dataclass

import pytest
from pytest_mock import MockerFixture

import otaclient_iot_logging_server.greengrass_config
from otaclient_iot_logging_server.greengrass_config import (
    get_profile_from_thing_name,
    IoTSessionConfig,
    PKCS11Config,
    parse_v1_config,
    parse_v2_config,
    parse_config,
)

from tests.conftest import TEST_DATA_DPATH

logger = logging.getLogger(__name__)

MODULE = otaclient_iot_logging_server.greengrass_config.__name__

# NOTE: AWS_PROFILE_INFO, GREENGRASS_V1_CONFIG and GREENGRASS_V2_CONFIG
#       environmental variables are properly set in pyproject.toml.
#       profile_info in configs.py is populated with aws_profile_info.yaml in tests/data.

# NOTE: gg_v1_cfg and gg_v2_cfg is the same, besides the thing_name,
#       this will be used as evidence to check which config is used.
GG_V1_CFG_FPATH = TEST_DATA_DPATH / "gg_v1_cfg.json"
GG_V1_CFG_RAW = GG_V1_CFG_FPATH.read_text()
CFG_FROM_GG_V1 = IoTSessionConfig(
    account_id="012345678901",
    ca_path="/greengrass/certs/root.ca.pem",
    private_key_path="/greengrass/certs/gg.private.key",
    certificate_path="/greengrass/certs/gg.cert.pem",
    thing_name="profile-dev-edge-ggv1-Core",
    profile="profile-dev",
    region="region",
    aws_credential_provider_endpoint="abcdefghijk01.credentials.iot.region.amazonaws.com",
)

GG_V2_CFG_FPATH = TEST_DATA_DPATH / "gg_v2_cfg.yaml"
GG_V2_CFG_RAW = GG_V2_CFG_FPATH.read_text()
CFG_FROM_GG_V2 = IoTSessionConfig(
    account_id="012345678901",
    ca_path="/greengrass/certs/root.ca.pem",
    private_key_path="/greengrass/certs/gg.private.key",
    certificate_path="/greengrass/certs/gg.cert.pem",
    thing_name="profile-dev-edge-ggv2-Core",
    profile="profile-dev",
    region="region",
    aws_credential_provider_endpoint="abcdefghijk01.credentials.iot.region.amazonaws.com",
)

GG_V2_TPM2_CFG_FPATH = TEST_DATA_DPATH / "gg_v2_cfg.yaml_tpm2.0"
GG_V2_TPM2_CFG_RAW = GG_V2_TPM2_CFG_FPATH.read_text()
CFG_FROM_GG_V2_TPM2 = IoTSessionConfig(
    account_id="012345678901",
    ca_path="/greengrass/certs/root.ca.pem",
    private_key_path="pkcs11:object=greengrass_key;type=private;pin-value=greengrass_userpin",
    certificate_path="pkcs11:object=greengrass_key;type=cert;pin-value=greengrass_userpin",
    thing_name="profile-dev-edge-ggv2-Core",
    profile="profile-dev",
    region="region",
    aws_credential_provider_endpoint="abcdefghijk01.credentials.iot.region.amazonaws.com",
    pkcs11_config=PKCS11Config(
        pkcs11_lib="/usr/lib/x86_64-linux-gnu/pkcs11/libtpm2_pkcs11.so",
        slot_id="1",
        user_pin="greengrass_userpin",
    ),
)


@pytest.mark.parametrize(
    "_in, _expected",
    [
        (f"thing/profile-stg-edge-{uuid.uuid1()}-Core", "profile-stg"),
        (f"profile-dev-edge-{uuid.uuid1()}-Core", "profile-dev"),
    ],
)
def test_get_profile_from_thing_name(_in: str, _expected: str):
    assert get_profile_from_thing_name(_in) == _expected


#
# ------ greengrass v1 configuration ------ #
#
# NOTE: support for ggv1 tpm2.0 is not implemented.
@pytest.mark.parametrize(
    "_raw_cfg, _expected",
    [(GG_V1_CFG_RAW, CFG_FROM_GG_V1)],
)
def test_parse_v1_config(_raw_cfg: str, _expected: IoTSessionConfig):
    assert parse_v1_config(_raw_cfg) == _expected


#
# ------ greengrass v2 configuration ------ #
#
@pytest.mark.parametrize(
    "_raw_cfg, _expected",
    [
        (GG_V2_CFG_RAW, CFG_FROM_GG_V2),
        (GG_V2_TPM2_CFG_RAW, CFG_FROM_GG_V2_TPM2),
    ],
)
def test_parse_v2_config(_raw_cfg: str, _expected: IoTSessionConfig):
    assert parse_v2_config(_raw_cfg) == _expected


#
# ------ test parse_config entry point ------ #
#
@dataclass
class _ServerConfig:
    GREENGRASS_V2_CONFIG: str
    GREENGRASS_V1_CONFIG: str


class TestParseConfig:
    def test_greengrass_v1_cfg_only(self, mocker: MockerFixture):
        _server_cfg = _ServerConfig(
            GREENGRASS_V1_CONFIG=str(GG_V1_CFG_FPATH),
            GREENGRASS_V2_CONFIG="/path/not/exists",
        )
        mocker.patch(f"{MODULE}.server_cfg", _server_cfg)

        assert parse_config() == CFG_FROM_GG_V1

    def test_greengrass_v2_cfg_only(self, mocker: MockerFixture):
        _server_cfg = _ServerConfig(
            GREENGRASS_V1_CONFIG="/path/not/exists",
            GREENGRASS_V2_CONFIG=str(GG_V2_CFG_FPATH),
        )
        mocker.patch(f"{MODULE}.server_cfg", _server_cfg)

        assert parse_config() == CFG_FROM_GG_V2

    def test_both_exist(self, mocker: MockerFixture):
        """
        Greengrass V2 config should take priority.
        """
        _server_cfg = _ServerConfig(
            GREENGRASS_V1_CONFIG=str(GG_V1_CFG_FPATH),
            GREENGRASS_V2_CONFIG=str(GG_V2_CFG_FPATH),
        )
        mocker.patch(f"{MODULE}.server_cfg", _server_cfg)
        assert parse_config() == CFG_FROM_GG_V2
