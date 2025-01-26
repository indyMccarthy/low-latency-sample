import websockets
import asyncio
import json
import socket


class HyperliquidClient:
    def __init__(self, logger):
        self.logger = logger
        self.websocket: websockets.WebSocketClientProtocol
        self.stop_event = asyncio.Event()

    def configure_socket(self, sock):
        """Configure socket for low latency"""
        if sock is None:
            return

        try:
            # Maximum performance settings
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            # sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_QUICKACK, 1)

            # Minimize buffering
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)

            # Set low latency mode (Linux)
            # sock.setsockopt(socket.SOL_SOCKET, socket.SO_BUSY_POLL, 50)
        except Exception as e:
            self.logger.warning(f"Failed to configure socket: {e}")

    async def connect(self):
        try:
            self.websocket = await websockets.connect("wss://api.hyperliquid.xyz/ws")

            # Get the underlying socket and configure it
            ws_socket = self.websocket.transport.get_extra_info("socket")
            self.configure_socket(ws_socket)

            print("Connected to WebSocket")
            asyncio.create_task(self._send_periodic_ping())
            return True
        except Exception as e:
            self.logger.error(f"WebSocket connection failed: {e}")
            return False

    async def _send_periodic_ping(self):
        ping_msg = {"method": "ping"}
        while not self.stop_event.is_set():
            try:
                await self.websocket.send(json.dumps(ping_msg))
                print("Ping sent")
            except Exception as e:
                print(f"Error sending ping: {e}")
                return
            await asyncio.sleep(30)

    def create_subscription(self, coin_symbol, subscription_type):
        return {
            "method": "subscribe",
            "subscription": {
                "type": subscription_type,
                "coin": coin_symbol,
            },
        }

    async def subscribe(self, coin_symbol):
        if not self.websocket:
            return False

        for feed in ["l2Book", "trades"]:
            msg = self.create_subscription(coin_symbol, feed)
            await self.websocket.send(json.dumps(msg))
            print(f"Subscribed to {feed} for {coin_symbol}")
        return True

    async def close(self):
        self.stop_event.set()
        if self.websocket:
            await self.websocket.close()
