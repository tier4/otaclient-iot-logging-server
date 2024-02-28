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

import pytest
from awsiot_credentialhelper.boto3_session import Boto3SessionProvider
from awsiot_credentialhelper.boto3_session import Pkcs11Config as aws_PKcs11Config
from pytest_mock import MockerFixture


import otaclient_iot_logging_server.boto3_session
from otaclient_iot_logging_server._utils import parse_pkcs11_uri
from otaclient_iot_logging_server.boto3_session import _convert_to_pem, get_session  # type: ignore
from otaclient_iot_logging_server.greengrass_config import (
    IoTSessionConfig,
    PKCS11Config,
)

from tests.conftest import TEST_DATA_DPATH

MODULE = otaclient_iot_logging_server.boto3_session.__name__

SAMPLE_CERT_PEM_FPATH = TEST_DATA_DPATH / "sample_cert.pem"
SAMPLE_CERT_DER_FPATH = TEST_DATA_DPATH / "sample_cert.der"


@pytest.mark.parametrize(
    "_in, _expected",
    [
        (
            pem_cert := SAMPLE_CERT_PEM_FPATH.read_bytes(),
            pem_cert,
        ),
        (SAMPLE_CERT_DER_FPATH.read_bytes(), pem_cert),
    ],
)
def test__convert_to_pem(_in: bytes, _expected: bytes):
    assert _convert_to_pem(_in) == _expected


_MOCKED_CERT = b"mocked_certs"
_PKCS11_PRIVKEY_URI = "pkcs11:object=greengrass_privkey;type=private"
_PARSED_PKCS11_PRIVKEY_URI = parse_pkcs11_uri(_PKCS11_PRIVKEY_URI)


@pytest.mark.parametrize(
    "_config, _expected_call",
    [
        # test#1: boto3 session without pkcs11
        (
            test1_cfg := IoTSessionConfig(
                account_id="test_account",
                ca_path="test_capath",
                private_key_path="test_privkey_path",
                certificate_path="test_cert_path",
                thing_name="test_thing_name",
                profile="test_profile",
                region="test_region",
                aws_credential_provider_endpoint="test_cred_endpoint",
            ),
            {
                "endpoint": test1_cfg.aws_credential_provider_endpoint,
                "role_alias": test1_cfg.aws_role_alias,
                "certificate": _MOCKED_CERT,
                "private_key": test1_cfg.private_key_path,
                "thing_name": test1_cfg.thing_name,
            },
        ),
        # test#2: boto3 session with pkcs11
        (
            test2_cfg := IoTSessionConfig(
                account_id="test_account",
                ca_path="test_capath",
                private_key_path=_PKCS11_PRIVKEY_URI,
                certificate_path="test_cert_path",
                thing_name="test_thing_name",
                profile="test_profile",
                region="test_region",
                aws_credential_provider_endpoint="test_cred_endpoint",
                pkcs11_config=(
                    test2_pkcs11_cfg := PKCS11Config(
                        pkcs11_lib="tpm2-pkcs11_lib",
                        slot_id="1",
                        user_pin="userpin",
                    )
                ),
            ),
            {
                "endpoint": test2_cfg.aws_credential_provider_endpoint,
                "role_alias": test2_cfg.aws_role_alias,
                "certificate": _MOCKED_CERT,
                "thing_name": test2_cfg.thing_name,
                "pkcs11": aws_PKcs11Config(
                    pkcs11_lib=test2_pkcs11_cfg.pkcs11_lib,
                    slot_id=int(test2_pkcs11_cfg.slot_id),
                    user_pin=test2_pkcs11_cfg.user_pin,
                    private_key_label=_PARSED_PKCS11_PRIVKEY_URI["object"],
                ),
            },
        ),
    ],
)
def test_get_session(
    _config: IoTSessionConfig, _expected_call: dict[str, Any], mocker: MockerFixture
):
    """
    Confirm with specific input IoTSessionConfig, we get the expected Boto3Session being created.
    """
    # ------ setup test ------ #
    _boto3_session_provider_mock = mocker.MagicMock(spec=Boto3SessionProvider)
    mocker.patch(f"{MODULE}.Boto3SessionProvider", _boto3_session_provider_mock)
    mocker.patch(
        f"{MODULE}._load_certificate", mocker.MagicMock(return_value=_MOCKED_CERT)
    )

    # ------ execution ------ #
    get_session(_config)

    # ------ check result ------ #
    _boto3_session_provider_mock.assert_called_once_with(**_expected_call)
