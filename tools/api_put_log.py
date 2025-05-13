import asyncio
import sys

import grpc

from otaclient_iot_logging_server.v1 import otaclient_iot_logging_server_v1_pb2 as pb2
from otaclient_iot_logging_server.v1 import (
    otaclient_iot_logging_server_v1_pb2_grpc as pb2_grpc,
)


async def run_put_log(log_message: str, server_address: str = "127.0.0.1:8084") -> None:
    """
    Simple gRPC client for PutLog API

    Args:
        log_message: The message to be logged
        server_address: Server address to connect to (e.g., "127.0.0.1:8084")
    """
    # Create async channel to server
    async with grpc.aio.insecure_channel(server_address) as channel:
        # Create stub
        stub = pb2_grpc.OTAClientIoTLoggingServiceStub(channel)

        try:
            # Create PutLogRequest directly
            # Note: PutLogRequest structure depends on how it's defined in your .proto file
            # This assumes the PutLogRequest has message, level, and timestamp fields
            request = pb2.PutLogRequest(
                ecu_id="autoware",
                log_type=pb2.LogType.LOG,
                message=log_message,
            )

            print(f"Sending log entry to {server_address}:")
            print(f"  Message: {log_message}")

            # Call PutLog API
            response = await stub.PutLog(request)

            # Display response
            print(f"PutLog response: {response}")

        except grpc.RpcError as e:
            print(f"RPC error: {e.code()}: {e.details()}")
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    # Parse command line arguments
    if len(sys.argv) < 2:
        print("Usage: python api_put_log.py 'log message' [server_address]")
        sys.exit(1)

    log_message = sys.argv[1]
    server_address = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1:8084"

    # Run async function
    asyncio.run(run_put_log(log_message, server_address))
