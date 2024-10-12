# OLIB - Øivind Lib

This is my personal utility library. It allows me to very quickly get a comfortable environment for writing different types apps. It is primarily focused on Python.

You'll see a mix of camelCase and snake_case in this lib. I recently convinced myself to start using snake_case for Python, but have not gone back and changed everything 🙂

## Using olib for a project

### Prerequisites

1. Install [uv](https://github.com/astral-sh/uv), a much faster package manager than pip
2. Install [autoenv](https://github.com/hyperupcall/autoenv) for automatically switching envs
3. Put the following in your `.bashrc` / `.zshrc`:

```
if [ -d $HOME/.autoenv ]; then
	export AUTOENV_ENV_FILENAME=.envrc
	export AUTOENV_ENV_LEAVE_FILENAME=.envrc.leave
	export AUTOENV_ENABLE_LEAVE=true

	source ~/.autoenv/activate.sh
fi
```

### Adding olib to a project

1. Add olib as submodule in the root of the project named 'olib'
2. Run ./olib/scripts/init.py


## Basic usage

You should now be able to use the `run` command as described further down

```
#Small subset of available commands
run -h            #Show help
run init          #Install packages
run py lint       #Run python lint
run py test       #Run python tests
run js lint       #Run javascript lint (if enabled)
run dev test-all  #Run all configured lints / tests
```

## Config file

To add additional features you can add a `config.py` file in the root of the project directory. The config file allows additional modules (templates) to be loaded into the `run` cli, including:
- Build and launch app using docker-compose
- Build and deploy app using k8s
- A remote CLI interface
- Provision postgres / mysql / redis / django / infisical for an app
- Connect to postgres / mysql / redis

An example config file is shown below. Let me know if you want more detail on this.

```
import parproc as pp
import sh

from olib.py.cli.run.templates import (
    buildSingleService,
    django,
    infisical,
    postgres,
    redis,
    remote,
)
from olib.py.cli.run.utils.remote import RemoteHost
from olib.py.django.conf.remote import conf_cli


@buildSingleService(
    category='apps',
    name='hello',
    servicePort=8000,
    localMountPort=80,
    deployments=['backend', 'celery-worker', 'celery-beat', 'frontend', 'static'],
    containers={
        'backend': './backend/Dockerfile.prod',
        'frontend': './frontend/Dockerfile.prod',
        'static': './infra/docker/Dockerfile.static',
    },
    compose='infra/docker/docker-compose.yml',
    helm_deploy='infra/k8s/hello',
    helm_migrate='infra/k8s/migration',
)
@postgres()
@redis()
@django(settings='hello.settings', django_working_dir='./backend')
@infisical()
@remote(
    plugins=[conf_cli],
    hosts=[
        RemoteHost('local', 'http://127.0.0.1:8000', try_creds=['user:pwd']),
    ],
)
class Config:
    displayName = 'Hello'
    insts = [
        {
            'name': 'hello-stage',
            'helm_values': ['infra/k8s/values.base.yml', 'infra/k8s/values.stage.yml'],
            'env_files': ['.env', '.env.production', '.env.production.stage'],
            'infisical_identity_id': '...',
            'pck_registry': 'pck-reg.home.arpa',
            'cluster': 'dev',
            '_nas': 'onas',
            'default': True,
        },
        {
            'name': 'hello-prod',
            'helm_values': ['infra/k8s/values.base.yml', 'infra/k8s/values.prod.yml'],
            'env_files': ['.env', '.env.production', '.env.production.prod'],
            'infisical_identity_id': '...',
            'pck_registry': 'pck-reg-pub.home.arpa',
            'cluster': 'pub',
            '_nas': 'ponas',
        },
    ]
    tools = ['python', 'javascript']
```

## Env file setup

Overview of different environment files that are / can be defined

 - .envrc: Sets up development environment, making olib work
 - .env: Base environment definitions. Loaded into env of all processes in all stages
 - .env.development: Loaded during local runs (next run, ./manage.py runserver, ./manage.py migrate)
 - .env.compose: Loaded during docker compose to help connect compose services
 - .env.production: Loaded during production
 - .env.production.stage: Loaded during production for staging environments
 - .env.production.prod: Loaded during production for production environments
