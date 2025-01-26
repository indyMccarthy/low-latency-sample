# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
import numpy as np
cimport numpy as np
from libc.math cimport pow

# Make sure numpy's int64 is available
np.import_array()

ctypedef np.int64_t DTYPE_INT

cpdef tuple calculate_ofi_cy(double[:] bid_prices, double[:] bid_sizes, np.int64_t[:] bid_counts,
                           double[:] ask_prices, double[:] ask_sizes, np.int64_t[:] ask_counts):
    cdef:
        double mid_price = (bid_prices[0] + ask_prices[0]) / 2.0
        double decay = 0.7
        double bid_pressure = 0.0
        double ask_pressure = 0.0
        int i
        double px, sz
        double diff

    for i in range(bid_prices.shape[0]):
        px = bid_prices[i]
        sz = bid_sizes[i]
        diff = abs(px - mid_price) / mid_price
        bid_pressure += sz * px * bid_counts[i] * pow(decay, diff)

    for i in range(ask_prices.shape[0]):
        px = ask_prices[i]
        sz = ask_sizes[i]
        diff = abs(px - mid_price) / mid_price
        ask_pressure += sz * px * ask_counts[i] * pow(decay, diff)

    cdef double total_pressure = bid_pressure + ask_pressure
    cdef double ofi = (bid_pressure - ask_pressure) / total_pressure if total_pressure > 0 else 0

    return ofi, mid_price

cpdef tuple simulate_slippage_cy(double[:] prices, double[:] sizes, double trade_size, double reference_price):
    cdef:
        double remaining_size = trade_size
        double total_cost = 0.0
        int i
        double volume, price
        double effective_price

    for i in range(prices.shape[0]):
        price = prices[i]
        volume = sizes[i]
        
        if remaining_size <= volume:
            total_cost += remaining_size * price
            break
        
        total_cost += volume * price
        remaining_size -= volume

    if trade_size > 0:
        effective_price = total_cost / trade_size
        return effective_price - reference_price, effective_price
    
    return 0.0, 0.0 