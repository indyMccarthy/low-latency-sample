import asyncio
from typing import Any, Dict
from websocket_client import HyperliquidClient
import websockets
import gc
from collections import deque
import time
from loguru import logger
import sys
import os
import platform
import orjson
import numpy as np
from src.optimized_metrics import calculate_ofi_cy, simulate_slippage_cy

from orderbook_metrics import calculate_ofi, calculate_spread, simulate_slippage

os.environ["MALLOC_CONF"] = "thp:always"

# Cross-platform CPU pinning
if platform.system() == "Linux":
    os.sched_setaffinity(0, {0})  # Pin to CPU 0
elif platform.system() == "Windows":
    import psutil

    psutil.Process().cpu_affinity([0])  # Pin to CPU 0

# Disable garbage collector to reduce jitter
gc.disable()

# Memory-efficient deque for processed message storage
queue = deque(maxlen=1000)  # Set a reasonable max size to avoid memory bloating

# Configure loguru for optimized, non-blocking asynchronous logging
logger.remove()  # Remove default handler
logger.add(
    "log.log",  # Log to a file
    level="INFO",  # Log level
    backtrace=False,  # Disable backtrace for faster logging
    enqueue=True,  # Enable async logging
    rotation="1 MB",  # Rotate log files after 1 MB
)
# Add console logging back
logger.add(sys.stderr, level="INFO")


# WebSocket server: listens for messages, processes data, and adds to the deque
async def websocket_handler(websocket, shutdown_event):
    logger.info("Client connected.")
    try:
        while not shutdown_event.is_set():
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=0.1)
                start_time = time.perf_counter_ns()  # Start timing in nanoseconds

                # Lightweight processing logic
                processed_message = process_message(message)

                # Add the processed message to the deque
                if processed_message:  # Only append if we have data
                    queue.append(processed_message)

                # Measure and log processing time
                end_time = time.perf_counter_ns()
                processing_time = (end_time - start_time) / 1000
                logger.info(f"Message processed in {processing_time:.4f} microseconds")
            except asyncio.TimeoutError:
                continue
    except websockets.exceptions.ConnectionClosed:
        logger.info("Client disconnected.")


def handle_orderbook_raw_py(data: Dict[str, Any]):
    """Handle order book updates."""
    try:

        # Extract data safely
        market_data = data.get("data", {})
        if not isinstance(market_data, dict):
            logger.error(f"Invalid orderbook data structure: {market_data}")
            return

        # Get levels from the correct path
        bids = market_data.get("levels", [[]])[0]  # First array is bids
        asks = market_data.get("levels", [[], []])[1]  # Second array is asks

        # Calculate metrics
        return {
            "spread": calculate_spread(data),
            "ofi": calculate_ofi(data)[0],
            "mid_price": calculate_ofi(data)[1],
            "slippage_long": simulate_slippage(data, trade_size=1, direction="B"),
            "slippage_short": simulate_slippage(data, trade_size=1, direction="A"),
            "book_depth": len(bids) + len(asks),
            "bid_volume": sum(float(level["sz"]) for level in bids),
            "ask_volume": sum(float(level["sz"]) for level in asks),
        }

    except Exception as e:
        logger.error(f"Error processing orderbook: {str(e)}", exc_info=True)


def handle_orderbook_cython(data: Dict[str, Any]):
    """Handle order book updates."""
    try:
        market_data = data["data"]
        levels = market_data["levels"]
        bids, asks = levels[0], levels[1]  # Direct array access

        # Convert to numpy arrays for faster processing
        bid_prices = np.array([float(b["px"]) for b in bids], dtype=np.float64)
        bid_sizes = np.array([float(b["sz"]) for b in bids], dtype=np.float64)
        bid_counts = np.array([int(b["n"]) for b in bids], dtype=np.int64)

        ask_prices = np.array([float(a["px"]) for a in asks], dtype=np.float64)
        ask_sizes = np.array([float(a["sz"]) for a in asks], dtype=np.float64)
        ask_counts = np.array([int(a["n"]) for a in asks], dtype=np.int64)

        # Calculate metrics using optimized functions
        ofi, mid_price = calculate_ofi_cy(bid_prices, bid_sizes, bid_counts, ask_prices, ask_sizes, ask_counts)

        slippage_long, _ = simulate_slippage_cy(ask_prices, ask_sizes, 1.0, ask_prices[0])
        slippage_short, _ = simulate_slippage_cy(bid_prices, bid_sizes, 1.0, bid_prices[0])

        return {
            "spread": ask_prices[0] - bid_prices[0],
            "mid_price": mid_price,
            "bid_top": bid_prices[0],
            "ask_top": ask_prices[0],
            "bid_size": bid_sizes[0],
            "ask_size": ask_sizes[0],
            "ofi": ofi,
            "slippage_long": slippage_long,
            "slippage_short": slippage_short,
            "book_depth": len(bids) + len(asks),
            "bid_volume": bid_sizes.sum(),
            "ask_volume": ask_sizes.sum(),
        }

    except Exception as e:
        logger.error(f"Error processing orderbook: {str(e)}")
        return None


def process_message(message: str):
    # Avoid using .get() for known message types
    data = orjson.loads(message)
    if data["channel"] == "l2Book":
        return handle_orderbook_cython(data)
    return None  # Return immediately for other message types


# Consumer: Reads messages from the deque and logs them
async def queue_consumer(shutdown_event):
    while not shutdown_event.is_set():
        if queue:
            # Pop from the left of the deque (FIFO)
            processed_message = queue.popleft()
            logger.debug(f"Processed message: {processed_message}")
        else:
            # Sleep briefly to avoid busy-waiting
            await asyncio.sleep(0)


# Main entry point: Start the WebSocket server and the consumer
async def main():
    # Create shutdown event within the main function
    shutdown_event = asyncio.Event()

    client = HyperliquidClient(logger)

    # Connect to WebSocket
    if not await client.connect():
        logger.error("Failed to connect to WebSocket")
        return False

    # Subscribe to feeds
    if not await client.subscribe("BTC"):
        logger.error("Failed to subscribe to feeds")
        await client.close()
        return False

    # Create tasks with shutdown_event parameter
    processor = asyncio.create_task(websocket_handler(client.websocket, shutdown_event))
    printer = asyncio.create_task(queue_consumer(shutdown_event))

    logger.info("Starting tasks...")

    try:
        # Wait for shutdown event
        await shutdown_event.wait()
        logger.info("Shutdown signal received, cleaning up...")
    except Exception as e:
        logger.error(f"Error in tasks: {e}")
    finally:
        # Clean up tasks if they're still running
        for task in [processor, printer]:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        await client.close()

    logger.info("Shutdown complete")


if __name__ == "__main__":
    # Set up and run the asyncio event loop with uvloop enabled
    asyncio.run(main())
