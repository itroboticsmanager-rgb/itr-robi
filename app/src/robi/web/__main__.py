"""Run the existing device service behind the browser kiosk, without a window."""

import argparse
from pathlib import Path

from ..config import Config


def main():
    parser = argparse.ArgumentParser(description="ROBI web kiosk service")
    parser.add_argument("--config", required=True, help="Existing device TOML; secrets stay on the device")
    parser.add_argument("--root", required=True, help="Built web interface directory")
    parser.add_argument("--port", type=int, default=4173)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if not (root / "index.html").is_file():
        parser.error("Build the web interface first: index.html is missing")
    config = Config.load(args.config)
    config.web.enabled, config.web.root, config.web.port = True, str(root), args.port
    if args.offline:
        config.crm.enabled = False
    # No invisible 1920x1280 pygame surfaces on a small fanless tablet.
    config.display.width, config.display.height = 640, 480
    config.display.target_fps = 30
    from ..bootstrap import App
    app = App(config, headless=True)
    try:
        app.boot()
        if app._web is None:
            raise RuntimeError("ROBI local web service could not start")
        print(f"ROBI web: http://127.0.0.1:{app._web.port}", flush=True)
        while True:
            app.step(app._tick_clock())
    except KeyboardInterrupt:
        pass
    finally:
        app.shutdown()


if __name__ == "__main__":
    main()
