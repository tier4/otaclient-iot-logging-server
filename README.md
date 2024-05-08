# OTAClient AWS IoT logging server

A logging server that uploads logs sent from otaclient to AWS cloudwatch.

This iot-logger is expected to be installed on the main ECU, with greengrass certificates and otaclient config file(ecu_info.yaml) installed.

## Usage

### Environmental variables

The behaviors of the iot_logging_server can be configured with the following environmental variables:

| Environmental variables | Default value | Description |
| ---- | ---- | --- |
| GREENGRASS_V1_CONFIG | `/greengrass/config/config.json` | |
| GREENGRASS_V2_CONFIG | `/greengrass/v2/init_config/config.yaml` | If both v1 and v2 config file exist, v2 will be used in prior. |
| AWS_PROFILE_INFO | `/opt/ota/iot_logger/aws_profile_info.yaml` | The location of AWS profile info mapping files. |
| ECU_INFO_YAML | `/boot/ota/ecu_info.yaml` | The location of ecu_info.yaml config file. iot-logger server will parse the config file and only process logs sending from known ECUs.|
| LISTEN_ADDRESS | `127.0.0.1` | The IP address iot-logger server listen on. By default only receive logs from local machine. |
| LISTEN_PORT | `8083` | |
| UPLOAD_LOGGING_SERVER_LOGS | `false` | Whether to upload the logs from server itself to cloudwatchlogs. |
| SERVER_LOGSTREAM_SUFFIX | `iot_logging_server` | log_stream_suffix to use for local server logs upload. |
| SERVER_LOGGING_LEVEL | `INFO` | The logging level of the server itself. |
| SERVER_LOGGING_LOG_FORMAT | `[%(asctime)s][%(levelname)s]-%(name)s:%(funcName)s:%(lineno)d,%(message)s` | |
| MAX_LOGS_BACKLOG | `4096` | Max pending log entries. |
| MAX_LOGS_PER_MERGE | `512` | Max log entries in a merge group. |
| UPLOAD_INTERVAL | `60` | Interval of uploading log batches to cloud. Note that if the logger is restarted before next upload occurs, the pending loggings will be dropped. |

### ecu_info.yaml

If `ecu_info.yaml` presented and valid, iot-logger will only accept logs from known ECU ids.
The known ECU ids are retrieved from parsing `ecu_info.secondaries` field.
Currently only ECU id will be checked, IP checking is not performed as sub ECU otaclient might send logging from different IPs if ECU has multiple interfaces.
