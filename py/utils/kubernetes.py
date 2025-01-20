# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~


import base64
import sys
import time

from urllib3.exceptions import MaxRetryError


def k8s_namespace_exists(name: str, context: str):
    from kubernetes import client, config

    config.load_kube_config(context=context)

    v1 = client.CoreV1Api()
    try:
        namespaces = v1.list_namespace()
        for ns in namespaces.items:
            if ns.metadata.name == name:
                return True
    except client.exceptions.ApiException as e:
        print(f"Failed to list namespaces: {e}")
        return False
    return False


def k8s_namespace_create(name: str, context: str, exist_ok=True):
    from kubernetes import client, config

    if k8s_namespace_exists(name, context=context):
        if not exist_ok:
            raise Exception(f'Namespace "{name}" already exists')

        return

    config.load_kube_config(context=context)
    v1 = client.CoreV1Api()

    namespace = client.V1Namespace(metadata=client.V1ObjectMeta(name=name))
    v1.create_namespace(namespace)


def k8s_secret_create(name: str, namespace: str, context: str, data: dict):
    from kubernetes import client, config

    config.load_kube_config(context=context)
    v1 = client.CoreV1Api()
    v1.create_namespaced_secret(
        namespace=namespace,
        body=client.V1Secret(
            metadata=client.V1ObjectMeta(name=name),
            data={k: base64.b64encode(v.encode('utf-8')).decode('utf-8') for k, v in data.items()},
        ),
    )


def k8s_secret_update(name: str, namespace: str, context: str, data: dict):
    from kubernetes import client, config

    config.load_kube_config(context=context)
    v1 = client.CoreV1Api()
    v1.replace_namespaced_secret(
        name=name,
        namespace=namespace,
        body=client.V1Secret(
            metadata=client.V1ObjectMeta(name=name),
            data={k: base64.b64encode(v.encode('utf-8')).decode('utf-8') for k, v in data.items()},
        ),
    )


def k8s_secret_create_or_update(name: str, namespace: str, context: str, data: dict):
    if k8s_secret_exists(name, namespace, context):
        k8s_secret_update(name, namespace, context, data)
    else:
        k8s_secret_create(name, namespace, context, data)


def k8s_secret_delete(name: str, namespace: str, context: str):
    from kubernetes import client, config

    config.load_kube_config(context=context)
    v1 = client.CoreV1Api()
    v1.delete_namespaced_secret(name=name, namespace=namespace)


def k8s_secret_read(name: str, namespace: str, context: str, exit_on_missing=True):
    from kubernetes import client, config

    config.load_kube_config(context=context)
    v1 = client.CoreV1Api()

    try:
        secret = v1.read_namespaced_secret(name=name, namespace=namespace)
    except client.exceptions.ApiException as e:
        print(f'Could not fetch secret "{name}": {e.reason} ({e.status})')

        if exit_on_missing:
            sys.exit(1)

    return {k: base64.b64decode(v).decode('utf-8') for k, v in secret.data.items()}


def k8s_secret_read_single(name: str, namespace: str, context: str, *keys: str):
    """Read a single key, however multiple name versions are allowed"""
    secrets = k8s_secret_read(name, namespace, context)

    for key in keys:
        if (val := secrets.get(key)) is not None:
            return val

    raise Exception(
        f'None of the secret keys "{', '.join(keys)}" are available in secret "{name}" in namespace "{namespace}"'
    )


def k8s_secret_exists(name: str, namespace: str, context: str):
    from kubernetes import client, config

    config.load_kube_config(context=context)
    v1 = client.CoreV1Api()

    try:
        v1.read_namespaced_secret(name=name, namespace=namespace)
    except client.exceptions.ApiException:
        return False

    return True


def k8s_job_create(image: str, command: list[str], jobName: str, namespace: str, context: str, pod_name=None):
    from kubernetes import client, config

    config.load_kube_config(context=context)
    batch_v1 = client.BatchV1Api()

    batch_v1.create_namespaced_job(
        body=client.V1Job(
            api_version='batch/v1',
            kind='Job',
            metadata=client.V1ObjectMeta(name=jobName),
            spec=client.V1JobSpec(
                template=client.V1PodTemplateSpec(
                    spec=client.V1PodSpec(
                        containers=[
                            client.V1Container(
                                name=pod_name or jobName,
                                image=image,
                                command=command,
                            )
                        ],
                        restart_policy='Never',
                    )
                )
            ),
        ),
        namespace=namespace,
    )


def k8s_pod_get_log(v1, podName: str, namespace: str, prev_log=None):
    """Returns log from job. If prev_log is provided, only log contents past prev_log is returned"""
    from kubernetes import client

    try:
        new_log = v1.read_namespaced_pod_log(name=podName, namespace=namespace)
        if prev_log:
            new_log = new_log[len(prev_log) :]

        return new_log

    except client.exceptions.ApiException:
        return ''


def k8s_job_wait_for_completion(jobName: str, namespace: str, context: str | None = None):
    """Rneturns true on success, false on error"""
    from kubernetes import client, config, watch

    config.load_kube_config(context=context)
    batch_v1 = client.BatchV1Api()
    v1 = client.CoreV1Api()
    w = watch.Watch()

    print('Waiting for job pod...')

    # Wait for the job to start, and get pod info
    pod = None
    for event in w.stream(v1.list_namespaced_pod, namespace):
        _pod = event['object']
        if _pod.metadata.labels.get('job-name') == jobName:
            pod = _pod
            break

    if pod is None:
        raise Exception('Pod not found')

    print(f"Found job pod: {pod.metadata.name}")
    print(f'Waiting for "{jobName}" to complete...')

    log = ''

    i = 0
    while True:
        try:
            api_response = batch_v1.read_namespaced_job_status(name=jobName, namespace=namespace)
        except MaxRetryError:
            # Unable to connect
            return False

        # Stream any log entries
        new_log = k8s_pod_get_log(v1, pod.metadata.name, namespace, log)

        if new_log:
            print(new_log, end='')
        log += new_log

        # Quit if job was done
        if api_response.status.succeeded or api_response.status.failed:
            i += 1
            if i > 3:
                return api_response.status.succeeded

        time.sleep(2)
