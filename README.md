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
