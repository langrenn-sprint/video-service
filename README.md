# video-service
A service to capture relevant video clips from an online camera

Start service:
.venv/bin/python3 -m video_service.app
But first, start dependencies (services & db):
docker-compose up event-service user-service photo-service mongodb

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

Install: curl <https://pyenv.run> | bash
Create: python -m venv .venv (replace .venv with your preferred name)
Install python 3.13: pyenv install 3.13
Activate:
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

## Running tests

We use [pytest](https://docs.pytest.org/en/latest/) for contract testing.

To run linters, checkers and tests:

```Zsh
% uv run poe release
```

To run tests with logging, do:

```Zsh
% uv run pytest -m integration -- --log-cli-level=DEBUG
```

### Push to docker registry manually (CLI)

docker-compose build
docker login ghcr.io -u github
password: Use a generated access token from GitHub (https://github.com/settings/tokens/1878556677)
docker tag ghcr.io/langrenn-sprint/video-service:test ghcr.io/langrenn-sprint/video-service:latest
docker push ghcr.io/langrenn-sprint/video-service:latest
