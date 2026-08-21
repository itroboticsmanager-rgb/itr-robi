"""Точка входу: `python -m robi`."""

from __future__ import annotations

import argparse
import sys

from .config import Config, ConfigError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="robi", description="ROBI device app")
    parser.add_argument("-c", "--config", help="шлях до device.toml")
    parser.add_argument("--offline", action="store_true", help="не підключатися до CRM")
    parser.add_argument("--headless", action="store_true", help="без вікна (SDL dummy)")
    parser.add_argument("--seconds", type=float, help="зупинитися через N секунд")
    args = parser.parse_args(argv)

    try:
        config = Config.load(args.config)
    except ConfigError as exc:
        print(f"конфігурація: {exc}", file=sys.stderr)
        return 2

    if args.offline:
        config.crm.enabled = False

    # Імпорт після розбору аргументів: pygame ініціалізує SDL, і робити це
    # заради `--help` немає сенсу.
    from .bootstrap import App

    app = App(config, headless=args.headless)
    stats = app.run(max_seconds=args.seconds)
    print(stats.as_row())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
