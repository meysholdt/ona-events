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
    return json.dumps(event_to_log_record(event), sort_keys=True, separators=(",", ":"))


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


def event_to_log_record(event: Any, enriched_data: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "watchEvent": to_payload(event),
        "enrichedData": enriched_data,
    }


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


def creator_email(client: Gitpod, environment: Any, errors: list[str]) -> str | None:
    creator_id = creator_id_from_environment(environment)
    creator_principal = creator_principal_from_environment(environment)
    if not creator_id or creator_principal != "PRINCIPAL_USER":
        return None

    try:
        user_response = client.users.get_user(user_id=creator_id)
        return getattr(getattr(user_response, "user", None), "email", None)
    except Exception as exc:
        errors.append(f"failed to fetch creator email for user {creator_id}: {exc}")
        return None


def runner_enrichment(client: Gitpod, runner_id: str | None, errors: list[str]) -> dict[str, Any] | None:
    if not runner_id:
        return None

    try:
        runner_response = client.runners.retrieve(runner_id=runner_id)
    except Exception as exc:
        errors.append(f"failed to fetch runner {runner_id}: {exc}")
        return None

    runner = runner_response.runner
    runner_spec = getattr(runner, "spec", None)
    runner_configuration = getattr(runner_spec, "configuration", None)
    runner_status = getattr(runner, "status", None)

    return {
        "id": getattr(runner, "runner_id", None),
        "name": getattr(runner, "name", None),
        "kind": getattr(runner, "kind", None),
        "provider": getattr(runner, "provider", None),
        "runnerManagerId": getattr(runner, "runner_manager_id", None),
        "region": getattr(runner_status, "region", None) or getattr(runner_configuration, "region", None),
        "statusPhase": getattr(runner_status, "phase", None),
        "systemDetails": getattr(runner_status, "system_details", None),
        "additionalInfo": to_payload(getattr(runner_status, "additional_info", None)),
    }


def machine_enrichment(client: Gitpod, environment: Any, runner_id: str | None, errors: list[str]) -> dict[str, Any]:
    spec = getattr(environment, "spec", None)
    status = getattr(environment, "status", None)
    spec_machine = getattr(spec, "machine", None)
    status_machine = getattr(status, "machine", None)

    return {
        "requestedClass": getattr(spec_machine, "class_", None),
        "phase": getattr(status_machine, "phase", None),
        "session": getattr(status_machine, "session", None),
        "timeout": getattr(status_machine, "timeout", None),
        "versions": to_payload(getattr(status_machine, "versions", None)),
        "failureMessage": getattr(status_machine, "failure_message", None),
        "warningMessage": getattr(status_machine, "warning_message", None),
        "runner": runner_enrichment(client, runner_id, errors),
    }


def environment_status_enrichment(environment: Any) -> dict[str, Any]:
    status = getattr(environment, "status", None)
    return {
        "phase": getattr(status, "phase", None),
        "statusVersion": getattr(status, "status_version", None),
        "failureMessage": getattr(status, "failure_message", None),
        "warningMessage": getattr(status, "warning_message", None),
    }


def enrich_environment_event(client: Gitpod, environment_id: str) -> dict[str, Any]:
    response = client.environments.retrieve(environment_id=environment_id)
    environment = response.environment
    metadata = getattr(environment, "metadata", None)
    status = getattr(environment, "status", None)
    content = getattr(status, "content", None)
    git = getattr(content, "git", None)
    initializer_git = first_initializer_git(environment)

    creator_id = creator_id_from_environment(environment)
    runner_id = getattr(metadata, "runner_id", None)
    errors: list[str] = []

    git_repo_url = getattr(git, "clone_url", None) or getattr(initializer_git, "remote_uri", None)
    branch = getattr(git, "branch", None)
    if branch is None and getattr(initializer_git, "target_mode", None) in {
        "CLONE_TARGET_MODE_REMOTE_BRANCH",
        "CLONE_TARGET_MODE_LOCAL_BRANCH",
    }:
        branch = getattr(initializer_git, "clone_target", None)

    enriched_data: dict[str, Any] = {
        "organizationId": getattr(metadata, "organization_id", None),
        "runnerId": runner_id,
        "creatorId": creator_id,
        "creatorEmail": creator_email(client, environment, errors),
        "projectId": getattr(metadata, "project_id", None),
        "gitRepoURL": git_repo_url,
        "gitRepoBranch": branch,
        "environmentStatus": environment_status_enrichment(environment),
        "machine": machine_enrichment(client, environment, runner_id, errors),
    }
    if errors:
        enriched_data["errors"] = errors

    return enriched_data


def enriched_log_record(client: Gitpod, event: Any) -> dict[str, Any]:
    resource_type = getattr(event, "resource_type", None)
    resource_id = getattr(event, "resource_id", None)

    if resource_type != "RESOURCE_TYPE_ENVIRONMENT":
        return event_to_log_record(event)

    if not resource_id:
        return event_to_log_record(
            event,
            {
                "error": "environment event did not include resourceId",
            },
        )

    try:
        return event_to_log_record(event, enrich_environment_event(client, resource_id))
    except Exception as exc:
        return event_to_log_record(
            event,
            {
                "error": f"failed to enrich environment {resource_id}: {exc}",
            },
        )


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
        print(json.dumps(enriched_log_record(client, event), sort_keys=True, separators=(",", ":")), flush=True)


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
