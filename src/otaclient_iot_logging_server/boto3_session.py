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

import subprocess
from pathlib import Path
from typing import Optional

from awsiot_credentialhelper.boto3_session import Boto3SessionProvider
from awsiot_credentialhelper.boto3_session import Pkcs11Config as aws_PKcs11Config
from OpenSSL import crypto

from otaclient_iot_logging_server._utils import parse_pkcs11_uri
from otaclient_iot_logging_server.greengrass_config import IoTSessionConfig


def _load_pkcs11_cert(
    pkcs11_lib: str,
    slot_id: str,
    private_key_label: str,
    user_pin: Optional[str] = None,
) -> bytes:
    """Load certificate from a pkcs11 interface(backed by a TPM2.0 chip).

    This function requires opensc and libtpm2-pkcs11-1 to be installed,
        and a properly setup and working TPM2.0 chip.
    """
    # fmt: off
    _cmd = [
        "/usr/bin/pkcs11-tool",
        "--module", pkcs11_lib,
        "--type", "cert",
        "--slot", slot_id,
        "--label", private_key_label,
        "--read-object",
    ]
    if user_pin:
        _cmd.extend(["--pin", user_pin])
    # fmt: on
    return subprocess.check_output(_cmd)


def _convert_to_pem(_data: bytes) -> bytes:
    """Unconditionally convert input cert to PEM format."""
    if _data.startswith(b"-----BEGIN CERTIFICATE-----"):
        return _data
    return crypto.dump_certificate(
        crypto.FILETYPE_PEM,
        crypto.load_certificate(crypto.FILETYPE_ASN1, _data),
    )


class Boto3Session:

    def __init__(self, config: IoTSessionConfig) -> None:
        self._config = config
        self._pkcs11_cfg = config.pkcs11_config

    def _load_certificate(self) -> bytes:
        """
        NOTE: Boto3SessionProvider only takes PEM format cert.
        """
        _path = self._config.certificate_path
        if _path.startswith("pkcs11"):
            assert (pkcs11_cfg := self._pkcs11_cfg)

            _parsed_cert_uri = parse_pkcs11_uri(_path)
            # NOTE: the cert pull from pkcs11 interface is in DER format
            return _convert_to_pem(
                _load_pkcs11_cert(
                    pkcs11_lib=pkcs11_cfg.pkcs11_lib,
                    slot_id=pkcs11_cfg.slot_id,
                    private_key_label=_parsed_cert_uri["object"],
                    user_pin=pkcs11_cfg.user_pin,
                )
            )
        return _convert_to_pem(Path(_path).read_bytes())

    def _get_session(self):
        """Get a session that using plain privkey."""
        config = self._config
        return Boto3SessionProvider(
            endpoint=config.aws_credential_provider_endpoint,
            role_alias=config.aws_role_alias,
            certificate=self._load_certificate(),
            private_key=config.private_key_path,
            thing_name=config.thing_name,
        ).get_session()

    def _get_session_pkcs11(self):
        """Get a session backed by privkey provided by pkcs11."""
        config = self._config
        assert (pkcs11_cfg := self._pkcs11_cfg)

        _parsed_key_uri = parse_pkcs11_uri(config.private_key_path)
        input_pkcs11_cfg = aws_PKcs11Config(
            pkcs11_lib=pkcs11_cfg.pkcs11_lib,
            slot_id=int(pkcs11_cfg.slot_id),
            user_pin=pkcs11_cfg.user_pin,
            private_key_label=_parsed_key_uri.get("object"),
        )

        return Boto3SessionProvider(
            endpoint=config.aws_credential_provider_endpoint,
            role_alias=config.aws_role_alias,
            certificate=self._load_certificate(),
            thing_name=config.thing_name,
            pkcs11=input_pkcs11_cfg,
        ).get_session()

    def get_session(self):
        if self._config.private_key_path.startswith("pkcs11"):
            return self._get_session_pkcs11()
        return self._get_session()
