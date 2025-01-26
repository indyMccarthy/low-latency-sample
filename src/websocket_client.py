import websockets
import asyncio
import json
import socket
import time
import random


class HyperliquidClient:
    def __init__(self, logger):
        self.logger = logger
        self.websocket = None
        self.stop_event = asyncio.Event()
        self.reconnect_delay = 1  # Start with 1 second delay
        self.max_reconnect_delay = 60  # Maximum delay between reconnection attempts
        self.connection_attempts = 0
        self.max_connection_attempts = 1000000  # Practically infinite
        self.last_message_time = time.time()
        self.heartbeat_interval = 30  # seconds

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
        while self.connection_attempts < self.max_connection_attempts and not self.stop_event.is_set():
            try:
                self.websocket = await websockets.connect(
                    "wss://api.hyperliquid.xyz/ws",
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=10,
                    max_size=2**23,  # 8MB max message size
                    compression=None,  # Disable compression for lower latency
                )

                # Get the underlying socket and configure it
                ws_socket = self.websocket.transport.get_extra_info("socket")
                self.configure_socket(ws_socket)

                self.connection_attempts = 0  # Reset counter on successful connection
                self.reconnect_delay = 1  # Reset delay
                self.logger.info("Connected to WebSocket")

                # Start heartbeat monitoring
                asyncio.create_task(self._monitor_connection())
                return True

            except Exception as e:
                self.logger.error(f"WebSocket connection failed: {e}")
                self.connection_attempts += 1

                # Exponential backoff with jitter
                jitter = random.uniform(0, 0.1) * self.reconnect_delay
                await asyncio.sleep(self.reconnect_delay + jitter)
                self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)

        return False

    async def _monitor_connection(self):
        """Monitor connection health and reconnect if needed"""
        while not self.stop_event.is_set():
            try:
                if time.time() - self.last_message_time > self.heartbeat_interval * 2:
                    self.logger.warning("Connection seems dead, initiating reconnect...")
                    await self.reconnect()
                await asyncio.sleep(5)
            except Exception as e:
                self.logger.error(f"Error in connection monitor: {e}")

    async def reconnect(self):
        """Handle reconnection and resubscription"""
        try:
            await self.websocket.close()
        except Exception as e:
            self.logger.error(f"Error closing WebSocket: {e}")

        if await self.connect():
            await self.subscribe("BTC")  # Resubscribe to feeds

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
