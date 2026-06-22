# ona-events

Demo Python app that subscribes to Ona's `WatchEvents` stream and logs every
received event to stdout as one JSON object per line.

## Setup

The app uses the Ona Python SDK published as `gitpod-sdk`.

```bash
python -m pip install -e .
```

Authentication uses `GITPOD_API_KEY` by default:

```bash
export GITPOD_API_KEY="<your-api-key>"
```

## Run

Watch organization-scoped events from the default host, `app.gitpod.io`:

```bash
ona-events
```

Use a different host:

```bash
ona-events --host staging.gitpod.io
```

Watch one environment, including its task, task execution, and service events:

```bash
ona-events --environment-id <environment-uuid>
```

Filter organization-scoped events by resource type:

```bash
ona-events --resource-type RESOURCE_TYPE_PROJECT --resource-type RESOURCE_TYPE_ENVIRONMENT
```

For nonstandard deployments, pass a full API URL:

```bash
ona-events --base-url https://example.com/api
```

## Log output

Each line is a JSON object with the original watch event separated from
data fetched through follow-up API calls:

```json
{
  "watchEvent": {
    "operation": "RESOURCE_OPERATION_UPDATE",
    "resourceId": "env-uuid",
    "resourceType": "RESOURCE_TYPE_ENVIRONMENT"
  },
  "enrichedData": {
    "organizationId": "org-uuid",
    "runnerId": "runner-uuid",
    "creatorId": "user-uuid",
    "creatorEmail": "creator@example.com",
    "projectId": "project-uuid",
    "gitRepoURL": "https://github.com/example/repo.git",
    "gitRepoBranch": "main",
    "environmentStatus": {
      "phase": "ENVIRONMENT_PHASE_RUNNING",
      "statusVersion": "42",
      "failureMessage": [],
      "warningMessage": []
    },
    "machine": {
      "requestedClass": "large",
      "phase": "PHASE_RUNNING",
      "session": "machine-session",
      "timeout": null,
      "versions": {
        "amiId": "ami-123",
        "supervisorCommit": "abc123",
        "supervisorVersion": "1.2.3"
      },
      "failureMessage": null,
      "warningMessage": null,
      "runner": {
        "id": "runner-uuid",
        "name": "aws-runner",
        "kind": "RUNNER_KIND_REMOTE",
        "provider": "RUNNER_PROVIDER_AWS_EC2",
        "runnerManagerId": "runner-manager-uuid",
        "region": "us-east-1",
        "statusPhase": "RUNNER_PHASE_ACTIVE",
        "systemDetails": "provider-specific details when available",
        "additionalInfo": [
          {"key": "privateIpAddress", "value": "10.0.0.5"},
          {"key": "instanceName", "value": "i-123"}
        ]
      }
    }
  }
}
```

Only environment events are enriched. Non-environment events are still logged
with the same top-level shape and `enrichedData` set to `null`.
Machine details are limited to what the Ona API exposes for the environment
and runner; provider-specific values such as IP address or EC2 instance name
appear under `machine.runner.additionalInfo` when present.
