# ona-events

Demo Python app that subscribes to Ona's `WatchEvents` stream, writes raw
events to `watchevents.log`, and prints selected environment enrichment fields
to stdout as formatted JSON.

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

## Log Output

Every raw watch event is written to `watchevents.log` as one JSON object per
line.

Environment events are enriched with follow-up API calls. For every enrichment,
the complete API data is written to `environment-details.log` as a formatted
JSON object:

```json
{
  "environment": {
    "id": "env-uuid",
    "metadata": {},
    "spec": {},
    "status": {}
  },
  "creator": {
    "id": "user-uuid",
    "email": "creator@example.com"
  },
  "runner": {
    "runnerId": "runner-uuid",
    "name": "aws-runner",
    "status": {}
  }
}
```

Stdout only receives the selected fields from enriched environment data as
formatted JSON:

```json
{
  "environmentID": "env-uuid",
  "operation": "RESOURCE_OPERATION_UPDATE",
  "organizationId": "org-uuid",
  "creatorId": "user-uuid",
  "creatorEmail": "creator@example.com",
  "projectId": "project-uuid",
  "gitRepoURL": "https://github.com/example/repo.git",
  "gitRepoBranch": "main",
  "phase": "ENVIRONMENT_PHASE_RUNNING",
  "awsAccountID": "123456789012",
  "region": "us-east-1",
  "runnerProxyDomain": "runner-proxy.example.com",
  "runnerID": "runner-uuid",
  "sessionID": "machine-session"
}
```

Only environment events are enriched and printed to stdout. Non-environment
events are only written to `watchevents.log`.
Machine details are limited to what the Ona API exposes for the environment
and runner. `awsAccountID` is populated from runner `additionalInfo` when the
API includes an AWS account field.
