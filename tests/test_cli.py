from __future__ import annotations

import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from gitpod.types.event_watch_response import EventWatchResponse

from ona_events_demo.cli import (
    ENVIRONMENT_DETAILS_LOG,
    build_base_url,
    selected_stdout_record,
)


class FakeEnvironments:
    def retrieve(self, *, environment_id: str):
        assert environment_id == "env-1"
        return SimpleNamespace(
            environment=SimpleNamespace(
                metadata=SimpleNamespace(
                    organization_id="org-1",
                    runner_id="runner-1",
                    creator=SimpleNamespace(id="user-1", principal="PRINCIPAL_USER"),
                    project_id="project-1",
                ),
                status=SimpleNamespace(
                    phase="ENVIRONMENT_PHASE_RUNNING",
                    status_version="42",
                    content=SimpleNamespace(
                        git=SimpleNamespace(
                            clone_url="https://github.com/acme/example.git",
                            branch="main",
                        )
                    ),
                    machine=SimpleNamespace(
                        phase="PHASE_RUNNING",
                        session="machine-session",
                        timeout=None,
                        versions=SimpleNamespace(
                            ami_id="ami-123",
                            supervisor_commit="abc123",
                            supervisor_version="1.2.3",
                        ),
                        failure_message=None,
                        warning_message=None,
                    ),
                    failure_message=[],
                    warning_message=[],
                ),
                spec=SimpleNamespace(
                    machine=SimpleNamespace(class_="large"),
                    content=SimpleNamespace(
                        initializer=SimpleNamespace(
                            specs=[
                                SimpleNamespace(
                                    git=SimpleNamespace(
                                        remote_uri="git@github.com:acme/from-initializer.git",
                                        clone_target="initializer-branch",
                                        target_mode="CLONE_TARGET_MODE_REMOTE_BRANCH",
                                    )
                                )
                            ]
                        )
                    ),
                ),
            )
        )


class FakeUsers:
    def get_user(self, *, user_id: str):
        assert user_id == "user-1"
        return SimpleNamespace(user=SimpleNamespace(email="creator@example.com"))


class FakeRunners:
    def retrieve(self, *, runner_id: str):
        assert runner_id == "runner-1"
        return SimpleNamespace(
            runner=SimpleNamespace(
                runner_id="runner-1",
                name="aws-runner",
                kind="RUNNER_KIND_REMOTE",
                provider="RUNNER_PROVIDER_AWS_EC2",
                runner_manager_id="runner-manager-1",
                spec=SimpleNamespace(configuration=SimpleNamespace(region="us-east-1")),
                status=SimpleNamespace(
                    phase="RUNNER_PHASE_ACTIVE",
                    region="us-east-2",
                    gateway_info=SimpleNamespace(
                        gateway=SimpleNamespace(
                            url="https://runner-proxy.example.com",
                            name="proxy",
                            region="us-east-2",
                        )
                    ),
                    system_details="m6i.large in VPC",
                    additional_info=[
                        SimpleNamespace(key="awsAccountID", value="123456789012"),
                        SimpleNamespace(key="privateIpAddress", value="10.0.0.5"),
                        SimpleNamespace(key="instanceName", value="i-123"),
                    ],
                ),
            )
        )


class FakeClient:
    environments = FakeEnvironments()
    users = FakeUsers()
    runners = FakeRunners()


class CliTests(unittest.TestCase):
    def test_build_base_url_defaults_to_app_api(self) -> None:
        self.assertEqual(build_base_url("app.gitpod.io"), "https://app.gitpod.io/api")

    def test_build_base_url_preserves_explicit_path(self) -> None:
        self.assertEqual(build_base_url("https://ona.example/custom"), "https://ona.example/custom/api")

    def test_selected_stdout_record_logs_full_environment_details(self) -> None:
        event = EventWatchResponse(
            resourceType="RESOURCE_TYPE_ENVIRONMENT",
            resourceId="env-1",
            operation="RESOURCE_OPERATION_UPDATE",
        )

        with TemporaryDirectory() as temp_dir, patch("ona_events_demo.cli.ENVIRONMENT_DETAILS_LOG", str(Path(temp_dir) / ENVIRONMENT_DETAILS_LOG)):
            record = selected_stdout_record(FakeClient(), event)
            details = (Path(temp_dir) / ENVIRONMENT_DETAILS_LOG).read_text(encoding="utf-8")
            detail_record = json.loads(details)

        self.assertEqual(
            record,
            {
                "environmentID": "env-1",
                "operation": "RESOURCE_OPERATION_UPDATE",
                "organizationId": "org-1",
                "creatorId": "user-1",
                "creatorEmail": "creator@example.com",
                "projectId": "project-1",
                "gitRepoURL": "https://github.com/acme/example.git",
                "gitRepoBranch": "main",
                "phase": "ENVIRONMENT_PHASE_RUNNING",
                "awsAccountID": "123456789012",
                "region": "us-east-2",
                "runnerProxyDomain": "runner-proxy.example.com",
                "runnerID": "runner-1",
                "sessionID": "machine-session",
            },
        )
        self.assertGreater(len(details.splitlines()), 1)
        self.assertEqual(detail_record["environment"]["metadata"]["organization_id"], "org-1")
        self.assertEqual(detail_record["creator"]["email"], "creator@example.com")
        self.assertEqual(detail_record["runner"]["kind"], "RUNNER_KIND_REMOTE")

    def test_non_environment_events_are_not_written_to_stdout(self) -> None:
        event = EventWatchResponse(
            resourceType="RESOURCE_TYPE_PROJECT",
            resourceId="project-1",
            operation="RESOURCE_OPERATION_UPDATE",
        )

        self.assertIsNone(selected_stdout_record(FakeClient(), event))


if __name__ == "__main__":
    unittest.main()
