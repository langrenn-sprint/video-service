### video-service
A service to capture relevant video clips from an online camera. The service can run as worker in 2 modes:

## CAPTURE_LOCAL
Capture video from a stream using Python libraries (cv2.VideoCapture), save as video clips in configurable resolution and duration. Video is stored locally and then uploaded to cloud bucket.

## DETECT
Line crossing detection. The service run as stand alone worker and pick up videos from the cloud bucket.
Configuration from database (default values in global_settings.json) will always be shared between the workers while each worker's mode will be defined through environment (env) configuration.

# storage settings
Sets usage of local file storage or cloud services such as Buckets
valid storage modes (VIDEO_STORAGE_MODE):
local_storage - pushing video to cloud bucket
cloud_storage - pushing image detectsions to cloud bucket

## Requirement for development

Install [uv](https://docs.astral.sh/uv/), e.g.:

```Zsh
% curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then install the dependencies:

```Zsh
% uv sync

```
### If required - virtual environment
```Zsh
curl https://pyenv.run | bash
python -m venv .venv
pyenv install 3.13
source .venv/bin/activate
```

### Start service in virtual env:
```Zsh
set -a
source .env
set +a
python -m video_service.app
Dependencies (services & db):
docker compose up integration-service race-service competition-format-service photo-service user-service event-service mongodb photo-service-gui
```

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
GOOGLE_CLOUD_PROJECT=sigma-celerity-257719
GOOGLE_STORAGE_BUCKET=langrenn-sprint
GOOGLE_STORAGE_SERVER=https://storage.googleapis.com
GOOGLE_CLOUD_REGION=europe-north1
MODE=CAPTURE_LOCAL
# Valid MODE values: CAPTURE_LOCAL, DETECT
# CAPTURE_LOCAL: Traditional Python video capture from URL
# DETECT: Line crossing detection

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

## test - urls
https://storage.googleapis.com/langrenn-sprint/photos/20240309_Ragde_lang.mp4
http://10.0.0.27:8080/video


## slette images og containere

```Shell
docker system prune -a --volumes
```

### Push to github docker registry manually (CLI)
docker compose build
docker login ghcr.io -u github
password: Use a generated access token from GitHub (https://github.com/settings/tokens/1878556677)
docker tag ghcr.io/langrenn-sprint/video-service:test ghcr.io/langrenn-sprint/video-service:latest
docker push ghcr.io/langrenn-sprint/video-service:latest


### Start service in google cloud run (only works in DETECT mode and with cloud_storage)

## Create artifact registry and grant access to your service account
gcloud artifacts repositories create docker-repository \
  --repository-format=docker \
  --location="europe-north1" \
  --description="Docker repository"

gcloud projects add-iam-policy-binding [PROJECT_ID] \
--member="serviceAccount:[SERVICE_ACCOUNT_EMAIL]" \
--role="roles/artifactregistry.writer"

## Upload Container
This is handled by github_actions - see .github/workflows/deploy_google.yml

## Start Cloud Run instance
- Go to Worker Pools and Click Deploy Container
- Select "Depoloy one revision" and paste container image uri (or select from the list)
- Configure scaling (recommendation: ?)
- Paste environment variables from this file - remember to modify passwords!
- Environment - make sure MODE = DETECT
- Click create!