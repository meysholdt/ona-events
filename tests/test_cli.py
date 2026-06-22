from __future__ import annotations

import unittest
from types import SimpleNamespace

from gitpod.types.event_watch_response import EventWatchResponse

from ona_events_demo.cli import (
    build_base_url,
    enriched_log_record,
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
                    system_details="m6i.large in VPC",
                    additional_info=[
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

    def test_enriched_log_record_separates_watch_event_and_enrichment(self) -> None:
        event = EventWatchResponse(
            resourceType="RESOURCE_TYPE_ENVIRONMENT",
            resourceId="env-1",
            operation="RESOURCE_OPERATION_UPDATE",
        )

        record = enriched_log_record(FakeClient(), event)

        self.assertEqual(
            record,
            {
                "watchEvent": {
                    "resourceType": "RESOURCE_TYPE_ENVIRONMENT",
                    "resourceId": "env-1",
                    "operation": "RESOURCE_OPERATION_UPDATE",
                },
                "enrichedData": {
                    "organizationId": "org-1",
                    "runnerId": "runner-1",
                    "creatorId": "user-1",
                    "creatorEmail": "creator@example.com",
                    "projectId": "project-1",
                    "gitRepoURL": "https://github.com/acme/example.git",
                    "gitRepoBranch": "main",
                    "environmentStatus": {
                        "phase": "ENVIRONMENT_PHASE_RUNNING",
                        "statusVersion": "42",
                        "failureMessage": [],
                        "warningMessage": [],
                    },
                    "machine": {
                        "requestedClass": "large",
                        "phase": "PHASE_RUNNING",
                        "session": "machine-session",
                        "timeout": None,
                        "versions": {
                            "ami_id": "ami-123",
                            "supervisor_commit": "abc123",
                            "supervisor_version": "1.2.3",
                        },
                        "failureMessage": None,
                        "warningMessage": None,
                        "runner": {
                            "id": "runner-1",
                            "name": "aws-runner",
                            "kind": "RUNNER_KIND_REMOTE",
                            "provider": "RUNNER_PROVIDER_AWS_EC2",
                            "runnerManagerId": "runner-manager-1",
                            "region": "us-east-2",
                            "statusPhase": "RUNNER_PHASE_ACTIVE",
                            "systemDetails": "m6i.large in VPC",
                            "additionalInfo": [
                                {"key": "privateIpAddress", "value": "10.0.0.5"},
                                {"key": "instanceName", "value": "i-123"},
                            ],
                        },
                    },
                },
            },
        )


if __name__ == "__main__":
    unittest.main()
