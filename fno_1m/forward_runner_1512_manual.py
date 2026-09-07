"""Manual 15:12 live WebSocket test harness with 15:11 setup candle and no production 15:05 stop.
This variant is for validation only and forces a 15:30 test stop."""
from __future__ import annotations
import forward_runner_1512 as base
from datetime import time
import forward_runner as runner
base.runner.TIME_EXIT = time(15,30)
runner.TIME_EXIT = time(15,30)
base.main()
