"""Safe local smoke test for Angel One connectivity.

No AlgoTest calls and no order placement. Prints live NSE F&O LTP only.
"""
from angel_live import run_data_only

if __name__ == "__main__":
    run_data_only()
