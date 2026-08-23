#!/usr/bin/env python3
"""KasbBook — entry point.

The bot lives in the `kasbbook` package, split by responsibility. This stays a
thin launcher so existing systemd units (ExecStart=.../bot.py) keep working.
"""
from kasbbook.app import main

if __name__ == "__main__":
    main()
