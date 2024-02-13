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
"""Greengrass config v1/v2 parsing implementation."""


from __future__ import annotations

import json
import logging
import re
from functools import partial
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urljoin

import yaml
from pydantic import computed_field

from otaclient_iot_logging_server._utils import (
    FixedConfig,
    NestedDict,
    chain_query,
    remove_prefix,
)
from otaclient_iot_logging_server.configs import profile_info, server_cfg

logger = logging.getLogger(__name__)


def get_profile_from_thing_name(_in: str) -> str:
    """Get profile from specific thing_name naming scheme.

    Schema: thing/<profile>-edge-<id>-Core
    """
    THINGNAME_PA = re.compile(
        r"^(thing[/:])?(?P<profile>[\w-]+)-edge-(?P<id>[\w-]+)-.*$"
    )

    _ma = THINGNAME_PA.match(_in)
    assert _ma, f"invalid resource id: {_in}"
    return _ma.group("profile")


class _ThingArn(NamedTuple):
    """ThingArn definition in NamedTuple.

    Format:
        arn:partition:service:region:account-id:resource-id
        arn:partition:service:region:account-id:resource-type/resource-id
        arn:partition:service:region:account-id:resource-type:resource-id

    Check https://docs.aws.amazon.com/IAM/latest/UserGuide/reference-arns.html for
        more details.
    """

    arn: str
    partition: str
    service: str
    region: str
    account_id: str
    resource_id: str

    @property
    def profile(self) -> str:
        return get_profile_from_thing_name(self.resource_id)

    @property
    def thing_name(self) -> str:
        return remove_prefix(self.resource_id, "thing/")


#
# ------ v1 configuration parse ------ #
#
regulate_path = partial(remove_prefix, _prefix="file://")


def parse_v1_config(_raw_cfg: str) -> IoTSessionConfig:
    """Parse Greengrass V1 config json and take what we need.

    Check https://docs.aws.amazon.com/greengrass/v1/developerguide/gg-core.html
        for example of full version of config.json.

    NOTE(20240207): not consider TPM for ggv1.
    """
    loaded_cfg = json.loads(_raw_cfg)
    assert isinstance(loaded_cfg, dict), f"invalid cfg: {_raw_cfg}"

    _raw_thing_arn = chain_query(loaded_cfg, "coreThing", "thingArn")
    thing_arn = _ThingArn(*_raw_thing_arn.split(":", 6))
    this_profile_info = profile_info.get_profile_info(thing_arn.profile)

    return IoTSessionConfig(
        account_id=thing_arn.account_id,
        ca_path=regulate_path(chain_query(loaded_cfg, "crypto", "caPath")),
        private_key_path=regulate_path(
            chain_query(
                loaded_cfg, "crypto", "principals", "IoTCertificate", "privateKeyPath"
            )
        ),
        certificate_path=regulate_path(
            chain_query(
                loaded_cfg, "crypto", "principals", "IoTCertificate", "certificatePath"
            )
        ),
        thing_name=thing_arn.thing_name,
        profile=this_profile_info.profile_name,
        region=thing_arn.region,
        aws_credential_provider_endpoint=str(this_profile_info.credential_endpoint),
    )


#
# ------ v2 configuration parse ------ #
#
def _v2_complete_uri(_cfg: NestedDict, _uri: str) -> str:
    """Fix up the URI if the URI is pkcs11 URI.

    In gg v2 config, the pin-value(userPin) are specified in
        aws.greengrass.crypto.Pkcs11Provider section, so these
        option is striped from priv_key/cert URI.

    As we will feed the URI to external openssl pkcs11 engine when using
        pycurl, we need to add the userPin information back to URI for openssl.

    Example pkcs11 URI schema:
    pkcs11:token=<token_label>;object=<key_label>;pin-value=<userpin>;type=<cert/private)>

    Args:
        _cfg: the dumped config file dict.
        _uri: the input uri for completing.

    Returns:
        Original input <_uri> if <_uri> is not a pkcs11 URI, else a completed
            pkcs11 URI with pin-value inserted.

    Raises:
        ValueError on failing complete a pkcs11 URI.
    """
    if not _uri.startswith("pkcs11:"):
        return _uri

    scheme, pkcs11_opts_str = _uri.split(":", maxsplit=1)
    pkcs11_opts_dict = {}
    for opt in pkcs11_opts_str.split(";"):
        k, v = opt.split("=", maxsplit=1)
        pkcs11_opts_dict[k] = v

    try:
        user_pin = chain_query(
            _cfg,
            "services",
            "aws.greengrass.crypto.Pkcs11Provider",
            "configuration",
            "userPin",
        )
        pkcs11_opts_dict["pin-value"] = user_pin
    except ValueError as e:
        raise ValueError(
            f"failed to complete pkcs11 URI: {e!r}\nconfig={_cfg}uri=\n{_uri} "
        )

    pkcs11_opts_str = (f"{k}={v}" for k, v in pkcs11_opts_dict.items())
    return f"{scheme}:{';'.join(pkcs11_opts_str)}"


def parse_v2_config(_raw_cfg: str) -> IoTSessionConfig:
    """Parse Greengrass V2 config yaml and take what we need.

    For TPM2.0, see
        https://docs.aws.amazon.com/greengrass/v2/developerguide/hardware-security.html.
        https://tier4.atlassian.net/wiki/spaces/HIICS/pages/2544042770/TPM+Ubuntu+22.04+Greengrass+v2.
        https://datatracker.ietf.org/doc/html/rfc7512.
    """
    loaded_cfg = yaml.safe_load(_raw_cfg)
    assert isinstance(loaded_cfg, dict), f"invalid cfg: {_raw_cfg}"

    thing_name = chain_query(loaded_cfg, "system", "thingName")
    this_profile_info = profile_info.get_profile_info(
        get_profile_from_thing_name(thing_name)
    )
    # NOTE(20240207): use credential endpoint defined in the config.yml in prior,
    #                 only when this information is not available, we use the
    #                 <_AWS_CREDENTIAL_PROVIDER_ENDPOINT_MAPPING> to get endpoint.
    _cred_endpoint: str = chain_query(
        loaded_cfg,
        "services",
        "aws.greengrass.Nucleus",
        "configuration",
        "iotCredEndpoint",
        default=None,
    )
    if _cred_endpoint is None:
        cred_endpoint = str(this_profile_info.credential_endpoint)
    else:
        cred_endpoint = f"https://{_cred_endpoint.rstrip('/')}/"

    return IoTSessionConfig(
        # NOTE: v2 config doesn't include account_id info
        account_id=this_profile_info.account_id,
        ca_path=chain_query(loaded_cfg, "system", "rootCaPath"),
        private_key_path=_v2_complete_uri(
            loaded_cfg, chain_query(loaded_cfg, "system", "privateKeyPath")
        ),
        certificate_path=_v2_complete_uri(
            loaded_cfg, chain_query(loaded_cfg, "system", "certificateFilePath")
        ),
        thing_name=thing_name,
        profile=this_profile_info.profile_name,
        region=chain_query(
            loaded_cfg,
            "services",
            "aws.greengrass.Nucleus",
            "configuration",
            "awsRegion",
        ),
        aws_credential_provider_endpoint=cred_endpoint,
    )


#
# ------ main config parser ------ #
#
class IoTSessionConfig(FixedConfig):
    """Configurations we need picked from parsed Greengrass V1/V2 configration file.

    Also check aws-iot-log-server.sh.j2 in ota_client_logger roles in
        autoware_ecu_system_setup repository for how the properties
        are created.
    """

    account_id: str
    ca_path: str
    private_key_path: str
    certificate_path: str
    thing_name: str
    profile: str
    region: str

    aws_credential_provider_endpoint: str

    @computed_field
    @property
    def aws_role_alias(self) -> str:
        return (
            f"{self.profile}-autoware-adapter-"
            "credentials-iot-secrets-access-role-alias"
        )

    @computed_field
    @property
    def aws_cloudwatch_log_group(self) -> str:
        return (
            f"/aws/greengrass/edge/{self.region}/"
            f"{self.account_id}/{self.profile}-edge-otaclient"
        )

    @computed_field
    @property
    def aws_credential_refresh_url(self) -> str:
        """The endpoint to refresh token from."""
        return urljoin(
            self.aws_credential_provider_endpoint,
            f"role-aliases/{self.aws_role_alias}/credentials",
        )


def parse_config() -> IoTSessionConfig:
    """Parse greengrass config v2/v1 and return IoTSessionConfig instance.

    NOTE: use greengrass config v2 in prior.
    """
    try:
        if (_v2_cfg_f := Path(server_cfg.GREENGRASS_V2_CONFIG)).is_file():
            _v2_cfg = parse_v2_config(_v2_cfg_f.read_text())
            logger.debug(f"gg config v2 is in used: {_v2_cfg}")
            return _v2_cfg

        _v1_cfg = parse_v1_config(Path(server_cfg.GREENGRASS_V1_CONFIG).read_text())
        logger.debug(f"gg config v1 is in used: {_v1_cfg}")
        return _v1_cfg
    except Exception as e:
        _msg = f"failed to parse config: {e!r}"
        logger.error(_msg)
        raise ValueError(_msg) from e
