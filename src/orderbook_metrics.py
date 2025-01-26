from typing import Tuple, Optional


def calculate_spread(order_book: dict) -> Optional[float]:
    """Calculate the bid-ask spread from the order book."""
    bids, asks = order_book["data"]["levels"]
    best_bid = float(bids[0]["px"]) if bids else 0
    best_ask = float(asks[0]["px"]) if asks else 0
    return best_ask - best_bid if best_ask and best_bid else None


def calculate_ofi(order_book: dict) -> Tuple[float, float]:
    """Calculate Order Flow Imbalance with price-level weighting."""
    bids, asks = order_book["data"]["levels"]

    # Calculate mid price
    mid_price = (float(bids[0]["px"]) + float(asks[0]["px"])) / 2

    # Calculate weighted pressures with decay
    decay = 0.7
    bid_pressure = sum(
        float(level["sz"])
        * float(level["px"])
        * level["n"]
        * (decay ** (abs(float(level["px"]) - mid_price) / mid_price))
        for level in bids
    )

    ask_pressure = sum(
        float(level["sz"])
        * float(level["px"])
        * level["n"]
        * (decay ** (abs(float(level["px"]) - mid_price) / mid_price))
        for level in asks
    )

    total_pressure = bid_pressure + ask_pressure
    ofi = (bid_pressure - ask_pressure) / total_pressure if total_pressure > 0 else 0

    return ofi, mid_price


def simulate_slippage(order_book, trade_size, direction="B"):
    """
    Simulate slippage for a hypothetical trade size.
    Args:
        order_book: JSON object containing bids and asks levels.
        trade_size: Hypothetical trade size.
        direction: "B" for bid/long or "A" for ask/short.
    Returns:
        tuple: (slippage_amount, effective_price, classification)
    """
    bids, asks = order_book["data"]["levels"]
    best_bid = float(bids[0]["px"])
    best_ask = float(asks[0]["px"])

    levels = asks if direction == "B" else bids
    reference_price = best_ask if direction == "B" else best_bid

    remaining_size = trade_size
    total_cost = 0

    for level in levels:
        price = float(level["px"])
        volume = float(level["sz"])
        if remaining_size <= volume:
            total_cost += remaining_size * price
            break
        total_cost += volume * price
        remaining_size -= volume

    if trade_size > 0:
        effective_price = total_cost / trade_size
        slippage = effective_price - reference_price  # For buys
        if direction == "A":
            slippage = reference_price - effective_price  # For sells

        classification = classify_slippage(slippage, reference_price)
        return slippage, effective_price, classification
    return None, None, None


def classify_slippage(slippage, reference_price):
    """
    Classify slippage relative to the reference price.
    Args:
        slippage: Slippage amount in dollars
        reference_price: Current best bid/ask price
    Returns:
        str: Classification of slippage
    """
    slippage_percent = abs(slippage) / reference_price * 100

    if slippage_percent < 0.0005:
        return "Very Low"
    elif slippage_percent < 0.002:
        return "Low"
    elif slippage_percent < 0.005:
        return "Moderate"
    elif slippage_percent < 0.01:
        return "High"
    else:
        return "Very High"
