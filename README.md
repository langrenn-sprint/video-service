# video-service
A service to capture relevant video clips from an online camera. The service can run as worker in 2 modes
### CAPTURE
Capture of a stream, save as video clips in configurable resolution and duration.
### DETECT
Line crossing detection. The service can run as stand alone worker or take input from worker CAPTURE.
Configuration from database (default values in global_settings.json) will always be shared between the workers wile each workers mode will be defined through environment (env) configuration.

# storage settings
Sets usage of local file storage or cloud services such as Buckets
valid storage modes (VIDEO_STORAGE_MODE):
local_storage - pushing video to cloud bucket
cloud_storage - pushing image detectsions to cloud bucket and message to pubsub

## Requirement for development

Install [uv](https://docs.astral.sh/uv/), e.g.:

```Zsh
% curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then install the dependencies:

```Zsh
% uv sync
```
Activate virtual env:
source .venv/bin/activate

### Install

% git clone <https://github.com/heming-langrenn/video-service.git>
% cd video-service

### Prepare .env filer (dummy parameter values supplied)

LOGGING_LEVEL=INFO
ADMIN_USERNAME=admin
ADMIN_PASSWORD=password
EVENTS_HOST_SERVER=localhost
EVENTS_HOST_PORT=8082
PHOTOS_HOST_SERVER=localhost
PHOTOS_HOST_PORT=8092
USERS_HOST_SERVER=localhost
USERS_HOST_PORT=8086
GOOGLE_APPLICATION_CREDENTIALS=/home/hh/github/secrets/application_default_credentials.json
GOOGLE_CLOUD_PROJECT=sigma-celerity-257719
GOOGLE_STORAGE_BUCKET=langrenn-sprint
GOOGLE_STORAGE_SERVER=https://storage.googleapis.comMODE=CAPTURE

## Running tests

We use [pytest](https://docs.pytest.org/en/latest/) for contract testing.

To run linters, checkers and tests:

```Zsh
% uv run poe release
```

To run tests with logging, do (/home/heming/Nedlastinger/20250525_GKOpp1.mp4):

```Zsh
% uv run pytest -m integration -- --log-cli-level=DEBUG
```

### Start service
```Zsh
source .venv/bin/activate
set -a
source .env
set +a
python -m video_service.app
Dependencies (services & db):
docker compose up event-service user-service photo-service mongodb
```

## slette images og containere

```Shell
docker system prune -a --volumes
```

### Push to docker registry manually (CLI)

docker compose build
docker login ghcr.io -u github
password: Use a generated access token from GitHub (https://github.com/settings/tokens/1878556677)
docker tag ghcr.io/langrenn-sprint/video-service:test ghcr.io/langrenn-sprint/video-service:latest
docker push ghcr.io/langrenn-sprint/video-service:latest


### Troubleshooting
Failed to create DNS resolver channel with automatic monitoring of resolver configuration changes.
```Zsh
echo fs.inotify.max_user_watches=524288 | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```