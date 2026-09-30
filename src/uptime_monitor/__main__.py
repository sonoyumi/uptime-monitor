"""Entry points: `python -m uptime_monitor` or the `uptime-monitor` command."""

import sys

from uptime_monitor.cli import main

if __name__ == "__main__":
    sys.exit(main())
