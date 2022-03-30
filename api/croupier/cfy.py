""" Cloudify python wrapper """
import time
import logging
from urllib.parse import urlparse
from django.conf import settings
from datetime import *

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


def upload_blueprint(path, blueprint_id, blueprint_file_name):
    error = None
    blueprint = None
    is_archive = bool(urlparse(path).scheme) or path.endswith(".tar.gz")

    client = _get_client()
    try:
        if is_archive:
            blueprint = client.blueprints.publish_archive(path, blueprint_id, blueprint_file_name)
        else:
            blueprint = client.blueprints.upload(path, blueprint_id)
    except CloudifyClientError as err:
        LOGGER.exception(err)
        error = str(err)

    return blueprint, error


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
        # LOGGER.info("Blueprint Info: " + str(blueprint_dict))
        LOGGER.info("Blueprint Info: " + str(blueprint_dict["plan"]["nodes"][1]["id"]))
        nodes = client.nodes.list(_include=['id', 'type', 'host_id'])
        for node in nodes:
            LOGGER.info("Blueprint Node: " + str(node))

        nodes_instances = client.node_instances.list(_include=['id', 'host_id'])
        for node_instance in nodes_instances:
            LOGGER.info("Blueprint Node Instance: " + str(node_instance))

        events = client.events.list(execution_id="f92ebd85-5d4b-4258-ad1c-d7f04d6f2ab7", node_id="job1",
                                    _include=['node_instance_id'])
        for event in events:
            LOGGER.info("Execute Event Node Instance: " + str(event))

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

    return deployment, error


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
    LOGGER.info("Execution: " + str(cfy_execution))
    events = client.events.list(
        execution_id=execution_id, _offset=offset, _size=100, include_logs=True
    )
    last_message = events.metadata.pagination.total
    LOGGER.info("Events msg: " + str(last_message))
    return {"logs": events.items, "last": last_message, "status": cfy_execution.status}


def get_execution_status(execution_id):
    client = _get_client()
    LOGGER.info("Checking last execution id: " + str(execution_id))

    # exec_list = client.executions.list()
    # LOGGER.info("Executions: " + str(exec_list))
    # Check if the deployment was never executed
    if execution_id is None:
        return Execution.TERMINATED, None

    # TODO: manage errors
    cfy_execution = client.executions.get(execution_id)

    return cfy_execution.status, cfy_execution.workflow_id


def get_execution(execution_id):
    client = _get_client()
    LOGGER.info("Execution id: " + str(execution_id))

    # Check if the deployment was never executed
    if execution_id is None:
        return None

    # TODO: manage errors
    # First of all, retrieve basic information from the Execution
    cfy_execution = client.executions.get(execution_id)
    LOGGER.info("Status: " + cfy_execution.status)
    LOGGER.info("End Time: " + str(cfy_execution.ended_at))
    LOGGER.info("Operations Finished: " + str(cfy_execution.finished_operations))
    LOGGER.info("Error: " + str(cfy_execution.error))

    # Obtain plan information from the Blueprint (Nodes)
    blueprint_plan = client.blueprints.get(blueprint_id=cfy_execution.blueprint_id, _include=['plan'])
    # LOGGER.info("Nodes List: " + str(blueprint_plan))
    LOGGER.info("Nodes List: " + str(blueprint_plan["plan"]["nodes"]))
    nodes_in_plan = blueprint_plan["plan"]["nodes"]
    nodes_list = []
    for node in nodes_in_plan:
        if node["type"] == "croupier.nodes.Job":
            nodes_list.append(node["id"])
            LOGGER.info("Found job node: " + str(node["id"]) + " of type " + str(node["type"]))

    # Obtain the Node Instances, corresponding to the Nodes for the current Execution Id (from Events)
    node_instances = set([])
    tasks_done = set([])
    ongoing_operation = 'None'
    ongoing_task = 'None'

    # instances_in_events = client.events.list(execution_id=execution_id, node_id=node,
    #                                         _include=['node_instance_id'])
    instances_in_events = client.events.list(execution_id=execution_id, sort='timestamp')

    # Let's iterate through all the events and detect tasks and operations status
    operations_done = set([])
    task_progress = 0.0
    num_errors = 0
    for node_instance in instances_in_events:
        node_instance_id = node_instance["node_instance_id"]
        LOGGER.info("Full node instance info: " + str(node_instance))
        LOGGER.info("Found node instance: " + str(node_instance_id))
        node_instances.add(node_instance_id)

        # Look at the operations and see which one is completed: queue, publish, cleanup
        node_event = node_instance["event_type"]
        node_operation = node_instance["operation"]
        LOGGER.info("Event: " + str(node_event) + " for operation: " + str(node_operation))

        if node_event == 'sending_task':
            ongoing_task = node_instance["node_name"]
            ongoing_operation = node_operation
            if node_operation == 'croupier.interfaces.lifecycle.publish':
                task_progress = 88.0
            elif node_operation == 'croupier.interfaces.lifecycle.cleanup':
                task_progress = 94.0
        elif node_event == 'task_succeeded':
            if node_operation == 'croupier.interfaces.lifecycle.queue':
                ongoing_operation = 'Executing task'
                operations_done.add(node_operation)
                LOGGER.info("Task " + ongoing_task + " was queued and is executing or waiting for execution.")
                task_progress = 8.0
            else:
                ongoing_operation = 'None'
                operations_done.add(node_operation)
                task_progress = 94.0
                if node_operation == 'croupier.interfaces.lifecycle.cleanup':
                    tasks_done.add(node_instance["node_name"])
                    ongoing_task = 'None'
                    task_progress = 100.0
        elif node_event == 'workflow_failed':
            num_errors = num_errors + 1

    LOGGER.info("Total list: " + str(nodes_list))
    LOGGER.info("Task progress: " + str(task_progress))
    LOGGER.info("Number of tasks: " + str(len(nodes_list)))

    # for node_instance in node_instances:
    #     # node_instance_info = client.node_instances.list(id=node_instance, _include=['id', 'host_id'])
    #     node_instance_info = client.node_instances.list(id=node_instance)
    #     LOGGER.info("Node Instance info: " + str(node_instance_info[0]))

    # operations_list = client.nodes.list(id=nodes_list[0], _include=['operations'])
    # task_graphs = client.tasks_graphs.list(execution_id, "run_jobs")
    # LOGGER.info("Number of workflows: " + str(len(task_graphs)))
    # for task_graph in task_graphs:
    #     LOGGER.info("Available workflow: " + str(task_graph))

    # for operation in operations_list:
    #    LOGGER.info("Node Operation info: " + str(operation["operations"]))

    # deployment_dict = client.deployments.get(cfy_execution["deployment_id"])
    # LOGGER.info("Deployment Info: " + str(deployment_dict))
    # workflows = deployment_dict["workflows"]
    # LOGGER.info("Available workflows: " + str(workflows))

    # operations_list = client.operations.list()
    # LOGGER.info("Operations Info: " + str(operations_list))

    # Calculate percentage of execution
    workflow_progress = 100.0
    if cfy_execution.status != 'terminated':
        workflow_progress = (100/len(nodes_list))*len(tasks_done) + task_progress/len(nodes_list)
    LOGGER.info("Total progress: " + str(workflow_progress))

    # Calculate total execution time of the instance
    execution_time = 0
    start_date = datetime.strptime(cfy_execution.started_at, "%Y-%m-%dT%H:%M:%S.%f%z")
    if cfy_execution.ended_at is None:
        end_date = datetime.now(timezone.utc)
        execution_time = end_date - start_date
    else:
        end_date = datetime.strptime(cfy_execution.ended_at, "%Y-%m-%dT%H:%M:%S.%f%z")
        execution_time = end_date - start_date

    execution_result = dict()
    execution_result['status'] = cfy_execution.status
    execution_result['end_time'] = cfy_execution.ended_at
    execution_result['total_tasks'] = len(nodes_list)
    execution_result['tasks_completed'] = len(tasks_done)
    execution_result['execution_time'] = execution_time.seconds
    execution_result['current_task'] = ongoing_task
    execution_result['current_operation'] = ongoing_operation
    execution_result['progress'] = workflow_progress
    execution_result['num_errors'] = num_errors
    execution_result['error_message'] = cfy_execution.error
    LOGGER.info("Execution info result: " + str(execution_result))

    return execution_result


def has_execution_ended(status):
    return status in Execution.END_STATES


def is_execution_finished(status):
    return status == Execution.TERMINATED


def is_execution_wrong(status):
    return has_execution_ended(status) and status != Execution.TERMINATED
