# low-latency-sample [WIP]

Low latency code in Python. This code sample uses the Hyperliquid websocket API to get orderbook data and calculate some metrics. Learn & practice project.

## Install

```bash
pip install .
```

If you want to build the `.pyx` file only, you can run:

```bash
python setup.py build_ext --inplace
```

This will create the `.pyd` and `.c` files in the `src` directory.

## Run

```bash
python src/main.py
```
