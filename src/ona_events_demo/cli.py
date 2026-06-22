from __future__ import annotations

import argparse
import json
import signal
import sys
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from gitpod import Gitpod

DEFAULT_HOST = "app.gitpod.io"


def build_base_url(host: str) -> str:
    host = host.strip().rstrip("/")
    if not host:
        raise ValueError("host must not be empty")

    if "://" not in host:
        host = f"https://{host}"

    parsed = urlsplit(host)
    path = parsed.path.rstrip("/")
    if not path:
        path = "/api"
    elif not path.endswith("/api"):
        path = f"{path}/api"

    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Subscribe to Ona WatchEvents and write each event to stdout as JSON.",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Ona host to connect to. Defaults to {DEFAULT_HOST}.",
    )
    parser.add_argument(
        "--base-url",
        help="Full Ona API base URL. Overrides --host when set.",
    )
    parser.add_argument(
        "--api-key",
        help="Ona API key. Defaults to the GITPOD_API_KEY environment variable.",
    )
    parser.add_argument(
        "--environment-id",
        help="Watch a single environment, including its task, task execution, and service events.",
    )
    parser.add_argument(
        "--resource-type",
        action="append",
        default=[],
        help="Organization-scope resource type filter. May be provided multiple times.",
    )
    return parser.parse_args(argv)


def event_to_json(event: Any) -> str:
    if hasattr(event, "model_dump"):
        payload = event.model_dump(mode="json", by_alias=True)
    elif hasattr(event, "dict"):
        payload = event.dict(by_alias=True)
    else:
        payload = event

    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def watch_events(args: argparse.Namespace) -> None:
    base_url = args.base_url.rstrip("/") if args.base_url else build_base_url(args.host)
    client = Gitpod(bearer_token=args.api_key, base_url=base_url)

    watch_kwargs: dict[str, Any]
    if args.environment_id:
        if args.resource_type:
            raise ValueError("--resource-type is only supported for organization-scope streams")
        watch_kwargs = {"environment_id": args.environment_id}
    else:
        watch_kwargs = {"organization": True}
        if args.resource_type:
            watch_kwargs["resource_type_filters"] = [
                {"resource_type": resource_type} for resource_type in args.resource_type
            ]

    for event in client.events.watch(**watch_kwargs):
        print(event_to_json(event), flush=True)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    try:
        watch_events(args)
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"ona-events: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
