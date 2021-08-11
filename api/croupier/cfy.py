""" Cloudify python wrapper """
import time
import logging
from urllib.parse import urlparse
from django.conf import settings

from cloudify_rest_client import CloudifyClient
from cloudify_rest_client.executions import Execution
from cloudify_rest_client.exceptions import (
    DeploymentEnvironmentCreationPendingError,
    DeploymentEnvironmentCreationInProgressError,
    CloudifyClientError,
)

# Get an instance of a logger
LOGGER = logging.getLogger(__name__)

WAIT_FOR_EXECUTION_SLEEP_INTERVAL = 5

# workflow types
INSTALL = "install"
RUN = "run_jobs"
UNINSTALL = "uninstall"

# possible status
READY = "ready"
TERMINATED = "terminated"
FAILED = "failed"
CANCELLED = "cancelled"
PENDING = "pending"
STARTED = "started"
CANCELLING = "cancelling"
FORCE_CANCELLING = "force_cancelling"


def _get_client():
    client = CloudifyClient(
        host=settings.ORCHESTRATOR_HOST,
        username=settings.ORCHESTRATOR_USER,
        password=settings.ORCHESTRATOR_PASS,
        tenant=settings.ORCHESTRATOR_TENANT,
        protocol="https"
    )
    return client


def upload_blueprint(path, blueprint_id):
    error = None
    blueprint = None
    is_archive = bool(urlparse(path).scheme) or path.endswith(".tar.gz")

    client = _get_client()
    try:
        if is_archive:
            blueprint = client.blueprints.publish_archive(path, blueprint_id)
        else:
            blueprint = client.blueprints.upload(path, blueprint_id)
    except CloudifyClientError as err:
        LOGGER.exception(err)
        error = str(err)

    return (blueprint, error)


def list_blueprints():
    error = None
    blueprints = None
    client = _get_client()
    try:
        blueprints = client.blueprints.list().items
    except CloudifyClientError as err:
        LOGGER.exception(err)
        error = str(err)

    return (blueprints, error)


def list_blueprint_inputs(blueprint_id):
    error = None
    data = None
    client = _get_client()
    try:
        blueprint_dict = client.blueprints.get(blueprint_id)
        inputs = blueprint_dict["plan"]["inputs"]
        data = [
            {
                "name": name,
                "type": input.get("type", "-"),
                "default": input.get("default", "-"),
                "description": input.get("description", "-"),
            }
            for name, input in inputs.items()
        ]
    except CloudifyClientError as err:
        LOGGER.exception(err)
        error = str(err)

    return data, error


def remove_blueprint(blueprint_id):
    error = None
    blueprint = None
    client = _get_client()
    try:
        blueprint = client.blueprints.delete(blueprint_id)
    except CloudifyClientError as err:
        LOGGER.exception(err)
        error = str(err)

    return blueprint, error


def list_deployments():
    error = None
    deployments = None
    client = _get_client()
    try:
        deployments = client.deployments.list().items
    except CloudifyClientError as err:
        LOGGER.exception(err)
        error = str(err)

    return deployments, error


def create_deployment(blueprint_id, instance_id, inputs):
    error = None
    deployment = None

    client = _get_client()
    try:
        deployment = client.deployments.create(
            blueprint_id,
            instance_id,
            inputs=inputs,
            skip_plugins_validation=True,  # FIXME skip_plugins_validation
        )
    except CloudifyClientError as err:
        LOGGER.exception(err)
        error = str(err)

    return deployment, error


def list_deployment_inputs(deployment_id):
    error = None
    data = None
    client = _get_client()
    try:
        deployment_dict = client.deployments.get(deployment_id)
        LOGGER.info("Deployment Info: " + str(deployment_dict))
        inputs = deployment_dict["inputs"]
        LOGGER.info("Available inputs: " + str(inputs))
        data = [
            {
                "name": name,
                "value": value,
            }
            for name, value in inputs.items()
        ]
    except CloudifyClientError as err:
        LOGGER.exception(err)
        error = str(err)

    return data, error


def destroy_deployment(instance_id, force=False):
    error = None
    deployment = None
    client = _get_client()
    try:
        deployment = client.deployments.delete(instance_id, ignore_live_nodes=force)
    except CloudifyClientError as err:
        LOGGER.exception(err)
        error = str(err)

    return (deployment, error)


def execute_workflow(deployment_id, workflow, force=False, params=None):
    error = None
    execution = None

    client = _get_client()
    while True:
        try:
            execution = client.executions.start(
                deployment_id, workflow, parameters=params, force=force
            )
            break
        except (
            DeploymentEnvironmentCreationPendingError,
            DeploymentEnvironmentCreationInProgressError,
        ) as err:
            LOGGER.warning(err)
            time.sleep(WAIT_FOR_EXECUTION_SLEEP_INTERVAL)
            continue
        except CloudifyClientError as err:
            error = str(err)
            LOGGER.exception(err)
        break

    return (execution, error)


def get_execution_events(execution_id, offset):
    client = _get_client()

    # TODO: manage errors
    cfy_execution = client.executions.get(execution_id)
    events = client.events.list(
        execution_id=execution_id, _offset=offset, _size=100, include_logs=True
    )
    last_message = events.metadata.pagination.total

    return {"logs": events.items, "last": last_message, "status": cfy_execution.status}


def get_execution_status(execution_id):
    client = _get_client()

    # TODO: manage errors
    cfy_execution = client.executions.get(execution_id)

    return (cfy_execution.status, cfy_execution.workflow_id)


def has_execution_ended(status):
    return status in Execution.END_STATES


def is_execution_finished(status):
    return status == Execution.TERMINATED


def is_execution_wrong(status):
    return has_execution_ended(status) and status != Execution.TERMINATED
