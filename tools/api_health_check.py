import asyncio

import grpc

from otaclient_iot_logging_server.v1 import otaclient_iot_logging_server_v1_pb2 as pb2
from otaclient_iot_logging_server.v1 import (
    otaclient_iot_logging_server_v1_pb2_grpc as pb2_grpc,
)


async def run_health_check(server_address: str = "127.0.0.1:8084") -> None:
    """
    Simple gRPC client for health check
    
    Args:
        server_address: Server address to connect to (e.g., "127.0.0.1:8084")
    """
    # Create async channel to server
    async with grpc.aio.insecure_channel(server_address) as channel:
        # Create stub
        stub = pb2_grpc.OTAClientIoTLoggingServiceStub(channel)
        
        try:
            # Create HealthCheckRequest
            request = pb2.HealthCheckRequest()
            print(f"Sending health check request to {server_address}...")
            
            # Call Check API
            response = await stub.Check(request)
            
            # Display response
            print(f"Health check response: {response}")
            print(f"Status: {response.status}")
            
        except grpc.RpcError as e:
            print(f"RPC error: {e.code()}: {e.details()}")
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    import sys
    
    # Get server address from command line arguments (default: 127.0.0.1:8084)
    server_address = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1:8084"
    
    # Run async function
    asyncio.run(run_health_check(server_address))