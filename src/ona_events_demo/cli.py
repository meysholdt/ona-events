from __future__ import annotations

import argparse
import json
import signal
import sys
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from gitpod import Gitpod

DEFAULT_HOST = "app.gitpod.io"
WATCH_EVENTS_LOG = "watchevents.log"
ENVIRONMENT_DETAILS_LOG = "environment-details.log"


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
        description="Subscribe to Ona WatchEvents, write raw events to log files, and print selected enrichment fields.",
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


def as_json(value: Any) -> str:
    return json.dumps(to_payload(value), sort_keys=True, separators=(",", ":"))


def as_formatted_json(value: Any) -> str:
    return json.dumps(to_payload(value), indent=2, sort_keys=True)


def write_json_line(path: str, value: Any) -> None:
    with open(path, "a", encoding="utf-8") as log_file:
        log_file.write(as_json(value))
        log_file.write("\n")


def write_formatted_json(path: str, value: Any) -> None:
    with open(path, "a", encoding="utf-8") as log_file:
        log_file.write(as_formatted_json(value))
        log_file.write("\n")


def to_payload(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, dict):
        return {key: to_payload(item) for key, item in value.items()}

    if isinstance(value, list):
        return [to_payload(item) for item in value]

    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)

    if hasattr(value, "dict"):
        return value.dict(by_alias=True)

    if hasattr(value, "__dict__"):
        return {key: to_payload(item) for key, item in vars(value).items()}

    return value


def event_to_json(event: Any) -> str:
    return as_json(event)


def creator_id_from_environment(environment: Any) -> str | None:
    metadata = getattr(environment, "metadata", None)
    creator = getattr(metadata, "creator", None)
    return getattr(creator, "id", None)


def creator_principal_from_environment(environment: Any) -> str | None:
    metadata = getattr(environment, "metadata", None)
    creator = getattr(metadata, "creator", None)
    return getattr(creator, "principal", None)


def first_initializer_git(environment: Any) -> Any | None:
    spec = getattr(environment, "spec", None)
    content = getattr(spec, "content", None)
    initializer = getattr(content, "initializer", None)
    specs = getattr(initializer, "specs", None) or []
    for initializer_spec in specs:
        git = getattr(initializer_spec, "git", None)
        if git:
            return git
    return None


def fetch_creator(client: Gitpod, environment: Any, errors: list[str]) -> Any | None:
    creator_id = creator_id_from_environment(environment)
    creator_principal = creator_principal_from_environment(environment)
    if not creator_id or creator_principal != "PRINCIPAL_USER":
        return None

    try:
        return client.users.get_user(user_id=creator_id)
    except Exception as exc:
        errors.append(f"failed to fetch creator email for user {creator_id}: {exc}")
        return None


def fetch_runner(client: Gitpod, runner_id: str | None, errors: list[str]) -> Any | None:
    if not runner_id:
        return None

    try:
        return client.runners.retrieve(runner_id=runner_id)
    except Exception as exc:
        errors.append(f"failed to fetch runner {runner_id}: {exc}")
        return None


def creator_email(creator_response: Any | None) -> str | None:
    return getattr(getattr(creator_response, "user", None), "email", None)


def additional_info_value(runner_response: Any | None, keys: set[str]) -> str | None:
    if runner_response is None:
        return None

    runner_status = getattr(getattr(runner_response, "runner", None), "status", None)
    for item in getattr(runner_status, "additional_info", None) or []:
        key = getattr(item, "key", None)
        if key in keys:
            return getattr(item, "value", None)
    return None


def runner_proxy_domain(runner_response: Any | None) -> str | None:
    if runner_response is None:
        return None

    runner_status = getattr(getattr(runner_response, "runner", None), "status", None)
    gateway_info = getattr(runner_status, "gateway_info", None)
    gateway = getattr(gateway_info, "gateway", None)
    gateway_url = getattr(gateway, "url", None)
    if not gateway_url:
        return None

    parsed = urlsplit(gateway_url)
    return parsed.netloc or parsed.path or gateway_url


def runner_region(runner_response: Any | None) -> str | None:
    if runner_response is None:
        return None

    runner = runner_response.runner
    runner_spec = getattr(runner, "spec", None)
    runner_configuration = getattr(runner_spec, "configuration", None)
    runner_status = getattr(runner, "status", None)
    return getattr(runner_status, "region", None) or getattr(runner_configuration, "region", None)


def environment_details_record(
    environment_response: Any,
    creator_response: Any | None,
    runner_response: Any | None,
    errors: list[str],
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "environment": to_payload(getattr(environment_response, "environment", None)),
        "creator": to_payload(getattr(creator_response, "user", None)),
        "runner": to_payload(getattr(runner_response, "runner", None)),
    }
    if errors:
        record["errors"] = errors
    return record


def selected_environment_fields(
    environment_response: Any,
    creator_response: Any | None,
    runner_response: Any | None,
    environment_id: str,
    operation: str | None,
    errors: list[str],
) -> dict[str, Any]:
    environment = environment_response.environment
    metadata = getattr(environment, "metadata", None)
    status = getattr(environment, "status", None)
    content = getattr(status, "content", None)
    git = getattr(content, "git", None)
    initializer_git = first_initializer_git(environment)

    creator_id = creator_id_from_environment(environment)
    runner_id = getattr(metadata, "runner_id", None)
    spec = getattr(environment, "spec", None)
    status_machine = getattr(status, "machine", None)

    git_repo_url = getattr(git, "clone_url", None) or getattr(initializer_git, "remote_uri", None)
    branch = getattr(git, "branch", None)
    if branch is None and getattr(initializer_git, "target_mode", None) in {
        "CLONE_TARGET_MODE_REMOTE_BRANCH",
        "CLONE_TARGET_MODE_LOCAL_BRANCH",
    }:
        branch = getattr(initializer_git, "clone_target", None)

    enriched_data: dict[str, Any] = {
        "environmentID": environment_id,
        "operation": operation,
        "organizationId": getattr(metadata, "organization_id", None),
        "creatorId": creator_id,
        "creatorEmail": creator_email(creator_response),
        "projectId": getattr(metadata, "project_id", None),
        "gitRepoURL": git_repo_url,
        "gitRepoBranch": branch,
        "phase": getattr(status, "phase", None),
        "awsAccountID": additional_info_value(runner_response, {"awsAccountID", "awsAccountId", "awsAccount"}),
        "region": runner_region(runner_response),
        "runnerProxyDomain": runner_proxy_domain(runner_response),
        "runnerID": runner_id,
        "sessionID": getattr(status_machine, "session", None) or getattr(getattr(spec, "machine", None), "session", None),
    }
    if errors:
        enriched_data["errors"] = errors

    return enriched_data


def enrich_environment_event(client: Gitpod, environment_id: str, operation: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
    response = client.environments.retrieve(environment_id=environment_id)
    environment = response.environment
    metadata = getattr(environment, "metadata", None)
    runner_id = getattr(metadata, "runner_id", None)
    errors: list[str] = []

    creator_response = fetch_creator(client, environment, errors)
    runner_response = fetch_runner(client, runner_id, errors)

    return (
        selected_environment_fields(response, creator_response, runner_response, environment_id, operation, errors),
        environment_details_record(response, creator_response, runner_response, errors),
    )


def selected_stdout_record(client: Gitpod, event: Any) -> dict[str, Any] | None:
    resource_type = getattr(event, "resource_type", None)
    resource_id = getattr(event, "resource_id", None)

    if resource_type != "RESOURCE_TYPE_ENVIRONMENT":
        return None

    if not resource_id:
        return {"error": "environment event did not include resourceId"}

    try:
        selected_fields, details_record = enrich_environment_event(client, resource_id, getattr(event, "operation", None))
        write_formatted_json(ENVIRONMENT_DETAILS_LOG, details_record)
        return selected_fields
    except Exception as exc:
        error_record = {"error": f"failed to enrich environment {resource_id}: {exc}"}
        write_formatted_json(ENVIRONMENT_DETAILS_LOG, {"environmentId": resource_id, **error_record})
        return error_record


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
        write_json_line(WATCH_EVENTS_LOG, event)
        stdout_record = selected_stdout_record(client, event)
        if stdout_record is not None:
            print(as_formatted_json(stdout_record), flush=True)


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
