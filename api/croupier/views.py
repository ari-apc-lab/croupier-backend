import json
import tempfile
# import pdb
import yaml
import logging

from django.http import JsonResponse
from rest_framework import status, viewsets
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from django.contrib.auth.models import User
from django.utils.dateparse import parse_datetime
from rest_framework.parsers import MultiPartParser

from requests import get

from datetime import *

from croupier import cfy
from croupier import vault
from croupier import marketplace
from croupier.models import (
    Application,
    AppInstance,
    InstanceExecution,
    DataCatalogueKey,
    ComputingInfrastructure,
    ComputingInstance,
)
from croupier.serializers import (
    ApplicationSerializer,
    AppInstanceSerializer,
    InstanceExecutionSerializer,
    DataCatalogueKeySerializer,
    ComputingInfrastructureSerializer,
    ComputingInstanceSerializer,
)

# Get an instance of a logger
LOGGER = logging.getLogger(__name__)


def serialize_blueprint_list(blueprints):
    data = []
    for blueprint in blueprints:
        entry = {
            'name': blueprint["id"],
            'description': blueprint["description"],
            'created': blueprint["created_at"],
            'updated': blueprint["updated_at"],
            'owner': blueprint["created_by"],
            'main_blueprint_file': blueprint["main_file_name"]}
        data.append(entry)
        # LOGGER.info("Blueprint received: " + str(entry))
    return data


def serialize_deployment_list(deployments):
    data = []
    for deployment in deployments:
        entry = {
            'name': deployment["id"],
            'description': deployment["description"],
            'created': deployment["created_at"],
            'updated': deployment["updated_at"],
            'owner': deployment["created_by"],
            'blueprint': deployment["blueprint_id"]}
        data.append(entry)
    return data


def synchronize_user_in_model(username):
    # Check if user exist, if not create it
    queryset = User.objects.all().filter(username=username)
    if len(queryset) == 0:
        user = User.objects.create_user(username=username,
                                        email='not given',
                                        password=username)
        LOGGER.info("User Created: " + str(user))
        return user
    else:
        LOGGER.info("User " + username + " found!")
        return queryset[0]


class ApplicationViewSet(viewsets.ModelViewSet):
    queryset = Application.objects.all()
    serializer_class = ApplicationSerializer
    permission_classes = [IsAuthenticated]  # TODO use roles
    parser_classes = [MultiPartParser]

    def list(self, request, *args, **kwargs):
        LOGGER.info("Requesting the list of Applications")
        blueprints = cfy.list_blueprints()

        # Synchronize blueprints returned from Cloudify with the internal model database of apps
        # Rational: blueprints could be uploaded/removed in Cloudify using its console, not necessarily using
        # the Hidalgo frontend
        data = serialize_blueprint_list(blueprints[0])
        self.synchronize_blueprint_list_in_model(data)

        # Filter results by name, if filter available
        name_filter = self.request.query_params.get('name')
        LOGGER.info("Name filter: " + str(name_filter))
        if name_filter is not None:
            apps = Application.objects.all().filter(name__icontains=name_filter)
            LOGGER.info("Number of apps to send: " + str(len(apps)))
        else:
            apps = Application.objects.all()
            LOGGER.info("Number of apps to send: " + str(len(apps)))

        # Filter results by ordered applications (from WooCommerce marketplace)
        auth_header = self.request.META.get('HTTP_AUTHORIZATION')
        user_token = auth_header.replace('Bearer ', '', 1)
        user_name = vault.get_user_info(user_token)
        LOGGER.info("User requesting: " + user_name)
        apps_allowed_list = marketplace.check_orders_for_user(user_name)
        LOGGER.info("Apps ordered: " + str(apps_allowed_list))
        apps = apps.filter(name__in=apps_allowed_list) | apps.filter(owner=user_name)
        LOGGER.info("Number of apps to send: " + str(len(apps)))

        serializer = ApplicationSerializer(apps, many=True)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):

        # Determine which user created the application
        auth_header = self.request.META.get('HTTP_AUTHORIZATION')
        user_token = auth_header.replace('Bearer ', '', 1)
        user_name = vault.get_user_info(user_token)
        LOGGER.info("App owner: " + user_name)
        synchronize_user_in_model(user_name)

        # Request is immutable by default
        _mutable = request.data._mutable
        request.data._mutable = True
        request.data["owner"] = user_name
        request.data["is_new"] = True
        request.data["is_advertised"] = False
        request.data["included"] = str(datetime.now(timezone.utc))
        request.data._mutable = _mutable
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Obtain the content from the uploaded file and leave it in temporary file
        tmp_package_file = tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False)
        temp_file_path = tmp_package_file.name
        LOGGER.info("Temp Blueprint file: " + str(temp_file_path))
        blueprint_package = request.data["blueprint_file"]
        LOGGER.info("Blueprint file: " + str(blueprint_package))
        # LOGGER.info("Blueprint file content: " + str(blueprint_package.read()))
        with open(temp_file_path, 'wb+') as destination:
            for chunk in blueprint_package.chunks():
                destination.write(chunk)

        # Create the application in the DDBB and upload the blueprint to Cloudify
        blueprint_yaml_file_name = request.data["main_blueprint_file"]
        blueprint_id = Application.create_blueprint_id(request.data["name"])
        _, err = cfy.upload_blueprint(temp_file_path, blueprint_id, blueprint_yaml_file_name)

        tmp_package_file.close()

        if err:
            return Response(err, status=status.HTTP_409_CONFLICT)

        # create blueprint on database
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    def retrieve(self, request, *args, **kwargs):
        LOGGER.info("Requesting details of an application...")
        instance = self.get_object()
        serializer = self.get_serializer(instance)

        # Retrieve the list of inputs of the blueprint
        inputs = cfy.list_blueprint_inputs(instance.blueprint_id())
        LOGGER.info("Inputs used: " + str(inputs))

        # Build the response with all the data
        complete_result = {}
        complete_result = serializer.data
        complete_result['inputs'] = json.dumps(inputs)
        LOGGER.info("Complete result: " + str(complete_result))

        return Response(complete_result)

    def update(self, request, *args, **kwargs):
        return Response(status=status.HTTP_403_FORBIDDEN)

    def partial_update(self, request, *args, **kwargs):
        return Response(status=status.HTTP_403_FORBIDDEN)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        if instance.owner != request.user:
            return Response(status=status.HTTP_403_FORBIDDEN)

        _, err = cfy.remove_blueprint(instance.blueprint_id())

        # If there's a disparity between Django and Cloudify we should delete no matter what
        self.perform_destroy(instance)
        if err:
            return Response(err, status=status.HTTP_409_CONFLICT)

        return Response(status=status.HTTP_204_NO_CONTENT)

    def synchronize_blueprint_list_in_model(self, blueprints):
        LOGGER.info("Number of blueprints found: " + str(len(blueprints)))

        # Take the full list of blueprints in the DDBB and check which ones should be removed
        # This is crucial, since blueprints in the DDBB, not present in Cloudify would fail execution
        all_internal_apps = Application.objects.all()
        for internal_app in all_internal_apps:
            app_found = any(internal_app.name == str(blueprint_properties['name']) for blueprint_properties
                            in blueprints)
            if not app_found:
                LOGGER.info("Remove blueprint: " + str(internal_app))
                internal_app.delete()

        # Go through the complete list of the orchestrator, in order to add and/or modify blueprints
        for blueprint in blueprints:
            # Check if blueprint exists in apps data model
            queryset = Application.objects.all().filter(name=blueprint['name'])

            if len(queryset) == 0:
                # If not, create an app from the blueprint and save it in the model
                # create blueprint on database
                # create user in user model if it does not exist
                synchronize_user_in_model(blueprint["owner"])
                blueprint.update({"included": str(datetime.now(timezone.utc))})
                blueprint.update({"is_new": "True"})
                blueprint.update({"is_updated": "False"})
                blueprint.update({"is_advertised": "False"})
                LOGGER.info("Add blueprint: " + str(blueprint))

                serializer = self.get_serializer(data=blueprint)
                if serializer.is_valid():
                    self.perform_create(serializer)
                    LOGGER.info("Application added!")
                else:
                    LOGGER.info(str(serializer.errors))
            else:
                # Check if the blueprint cannot be considered 'new' anymore (new < 10 days) or if it was updated
                actual_object = queryset[0]
                inclusion_date = actual_object.included
                update_date = actual_object.updated
                today_date = datetime.now(timezone.utc)
                is_change = False

                # Change status from new to not new?
                if actual_object.is_new and (inclusion_date + timedelta(days=10)) < today_date:
                    actual_object.is_new = False
                    is_change = True
                    LOGGER.info("Blueprint not new anymore.")

                # Update fields if it was updated in the Cloudify instance
                if update_date < datetime.strptime(blueprint["updated"], "%Y-%m-%dT%H:%M:%S.%f%z"):
                    actual_object.is_updated = True
                    actual_object.description = blueprint["description"]
                    actual_object.main_blueprint_file = blueprint["main_blueprint_file"]
                    actual_object.updated = blueprint["updated"]
                    is_change = True
                    LOGGER.info("Blueprint updated.")

                # Update the blueprint information in the model (if there are changes)
                if is_change:
                    actual_object.save()
                    LOGGER.info("Updated blueprint info: " + actual_object.name)

    @action(detail=False)
    def reset(self, request, *args, **kwargs):
        Application.objects.all().delete()
        return Response("Applications (Blueprints) reset in database", status=status.HTTP_200_OK)


class AppInstanceViewSet(viewsets.ModelViewSet):
    queryset = AppInstance.objects.all()
    serializer_class = AppInstanceSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    def list(self, request, *args, **kwargs):
        LOGGER.info("Requesting the list of Instances")
        deployments = cfy.list_deployments()
        # LOGGER.info("Deployments Available: " + str(deployments))
        # Synchronize deployments returned from Cloudify with the internal model database of application instances
        # For each returned deployment, check if the deployment exits in the internal database by name
        # If not, create the app and store it in the database
        # Rational: deployments could be created in Cloudify using its console, not necessarily using
        # the Hidalgo frontend
        data = serialize_deployment_list(deployments[0])
        self.synchronize_deployment_list_in_model(data)

        # Filter results by name, if filter available
        name_filter = self.request.query_params.get('name')
        LOGGER.info("Name filter: " + str(name_filter))
        app_filter = self.request.query_params.get('app')
        LOGGER.info("App filter: " + str(app_filter))
        created_filter = self.request.query_params.get('created')
        LOGGER.info("Created filter: " + str(created_filter))

        # Filter results by owner
        auth_header = self.request.META.get('HTTP_AUTHORIZATION')
        user_token = auth_header.replace('Bearer ', '', 1)
        user_name = vault.get_user_info(user_token)
        LOGGER.info("Author filter: " + user_name)

        # Obtain all the instances as first query
        instances = AppInstance.objects.all()

        # Filter by name if available
        if name_filter is not None:
            instances = instances.filter(name__icontains=name_filter)
            LOGGER.info("Name filter. Number of instances to send: " + str(len(instances)))

        # Filter by app if available
        if app_filter is not None:
            instances = instances.filter(app__name__icontains=app_filter)
            LOGGER.info("App filter. Number of instances to send: " + str(len(instances)))

        if created_filter is not None:
            instances = instances.filter(created__gte=datetime.strptime(created_filter, "%Y-%m-%dT%H:%M:%S.%f%z"))
            LOGGER.info("Date filter. Number of instances to send: " + str(len(instances)))

        # Filter by owner
        instances = instances.filter(owner=user_name)
        LOGGER.info("Owner filter. Number of instances to send: " + str(len(instances)))

        serializer = AppInstanceSerializer(instances, many=True)
        return Response(serializer.data)

    # def get_queryset(self):
    #    user = self.request.user
    #    LOGGER.info("User requesting actions: " + str(user))
    #    return AppInstance.objects.filter(owner=user)

    def create(self, request, *args, **kwargs):
        # Check Application Instance with given name does not exist. Otherwise reject creation
        try:
            instance = AppInstance.getByName(request.data["name"])
            if instance is not None:
                return Response("Application instance with name {} already created".format(request.data["name"]),
                                status=status.HTTP_409_CONFLICT)
        except Exception as ex:
            pass  # Instance does not exist, proceeding with creation

        # Modify author's information and create the user if it doesn't exist
        request.data._mutable = True
        auth_header = self.request.META.get('HTTP_AUTHORIZATION')
        user_token = auth_header.replace('Bearer ', '', 1)
        user_name = vault.get_user_info(user_token)
        request.data["owner"] = user_name
        synchronize_user_in_model(user_name)

        # Retrieve basic information (for consistency checking)
        blueprint_id = request.data["app"]
        deployment_id = request.data["name"]

        # Obtain the content from the uploaded file and leave it in temporary file
        tmp_package_file = tempfile.NamedTemporaryFile(suffix=".yaml", delete=False)
        temp_file_path = tmp_package_file.name
        LOGGER.info("Temp YAML file: " + str(temp_file_path))
        deployment_file = request.data["inputs_file"]
        LOGGER.info("Iputs file: " + str(deployment_file))
        # LOGGER.info("Iputs file content: " + str(deployment_file.read()))
        with open(temp_file_path, 'wb+') as destination:
            for chunk in deployment_file.chunks():
                destination.write(chunk)

        # Load the temporary file in order to obtain the YAML inputs in dict structure
        inputs = None
        # example_file = "C:\\HiDALGO\\Demo\\ECMWF\\ecmwf-publish-blueprint-inputs-basic.yaml"
        with open(temp_file_path, 'r') as my_yaml_file:
            inputs = yaml.safe_load(my_yaml_file)
            LOGGER.info("Iputs from YAML: " + str(inputs))

        # Execute the call to create a new deployment with the information provided
        _, err = cfy.create_deployment(
            blueprint_id, deployment_id, inputs
        )

        if err:
            return Response(err, status=status.HTTP_409_CONFLICT)

        # Execute install workflow
        execution, err = cfy.execute_workflow(deployment_id, cfy.INSTALL)

        if err:
            return Response(err, status=status.HTTP_409_CONFLICT)

        # Create deployment on database. If it were to fail, reverse the process on Cloudify
        try:
            request.data["last_execution"] = execution["id"]
            request.data["created"] = execution["created_at"]
            request.data["updated"] = execution["created_at"]
            request.data["is_new"] = True
            app = Application.getByName(request.data["app"])
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save(app=app)
        except Exception as ex:
            cfy.execute_workflow(deployment_id, cfy.UNINSTALL)
            cfy.destroy_deployment(deployment_id)
            return Response(ex, status=status.HTTP_409_CONFLICT)
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    def retrieve(self, request, *args, **kwargs):
        LOGGER.info("Requesting details of an instance...")
        instance = self.get_object()

        # Retrieve user's token to check in Keycloak
        auth_header = self.request.META.get('HTTP_AUTHORIZATION')
        user_token = auth_header.replace('Bearer ', '', 1)
        LOGGER.info("Security token: " + str(user_token))
        token_info = vault.get_user_info(user_token)
        LOGGER.info("User name: " + token_info)

        # Use security token to retrieve user name and check authorization for the object
        # if instance.owner != request.user:
        #    return Response(status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(instance)
        LOGGER.info("Instance info: " + str(serializer.data))

        # Retrieve the list of inputs used in the deployment
        inputs = cfy.list_deployment_inputs(instance.deployment_id())

        # Build the response with all the data
        complete_result = {}
        complete_result = serializer.data
        # complete_result['inputs'] = inputs
        complete_result['inputs'] = json.dumps(inputs, ensure_ascii=False)
        LOGGER.info("Complete result: " + str(complete_result))

        return Response(complete_result)

    def update(self, request, *args, **kwargs):
        return Response(status=status.HTTP_403_FORBIDDEN)

    def partial_update(self, request, *args, **kwargs):
        return Response(status=status.HTTP_403_FORBIDDEN)

    @action(methods=["post"], detail=True)
    def execute(self, request, pk=None):
        # instance = self.get_object()
        instance = AppInstance.objects.get(pk=pk)
        LOGGER.info("Current instance for execution: " + str(self.get_serializer(instance).data))

        # Collect user info and check it's the adequate one
        auth_header = self.request.META.get('HTTP_AUTHORIZATION')
        user_token = auth_header.replace('Bearer ', '', 1)
        user_name = vault.get_user_info(user_token)
        LOGGER.info("User executing: " + user_name)
        # if instance.owner != request.user:
        #    return Response(status=status.HTTP_403_FORBIDDEN)

        current_status, wf_type = cfy.get_execution_status(instance.last_execution)

        if wf_type == cfy.INSTALL and cfy.is_execution_wrong(current_status):
            return Response(status=status.HTTP_424_FAILED_DEPENDENCY)

        if not cfy.has_execution_ended(current_status):
            return Response(status=status.HTTP_423_LOCKED)

        # execute run_jobs
        execution, err = cfy.execute_workflow(instance.deployment_id(), cfy.RUN)
        if err:
            return Response(err, status=status.HTTP_409_CONFLICT)

        # update the instance with the latest execution
        serializer = self.get_serializer(
            instance, data={"last_execution": execution["id"]}, partial=True
        )
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        # create new execution element
        new_execution_id = execution["id"]
        new_execution_date = datetime.now(timezone.utc)
        new_execution_owner = User.objects.get(username=user_name)
        new_execution = InstanceExecution(id=new_execution_id, instance=instance, created=new_execution_date,
                                          owner=new_execution_owner)
        new_execution.save()
        LOGGER.info("New execution created: " + new_execution_id)

        return Response(serializer.data)

    @action(methods=["get"], detail=True)
    def events(self, request, pk=None):
        instance = self.get_object()

        # if instance.owner != request.user:
        #    return Response(status=status.HTTP_403_FORBIDDEN)

        # offset = request.data["offset"]
        offset = 0

        data = cfy.get_execution_events(instance.last_execution, offset)
        return Response(data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        if instance.owner != request.user:
            return Response(status=status.HTTP_403_FORBIDDEN)

        # execute uninstall
        _, err = cfy.execute_workflow(
            instance.deployment_id(), cfy.UNINSTALL, force=True
        )
        if err:
            return Response(err, status=status.HTTP_409_CONFLICT)

        _, err = cfy.destroy_deployment(instance.deployment_id())
        if err:
            return Response(err, status=status.HTTP_409_CONFLICT)

        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def synchronize_deployment_list_in_model(self, deployments):
        LOGGER.info("Number of deployments found: " + str(len(deployments)))

        # Take the full list of deployments in the DDBB and check which ones should be removed
        # This is crucial, since deployments in the DDBB, not present in Cloudify would fail execution
        all_internal_instances = AppInstance.objects.all()
        LOGGER.info("Number of deployments stored: " + str(len(all_internal_instances)))
        for internal_app_instance in all_internal_instances:
            app_instance_found = any(internal_app_instance.name == str(deployment_properties['name']) for
                                     deployment_properties in deployments)
            if not app_instance_found:
                LOGGER.info("Remove deployment: " + str(internal_app_instance))
                internal_app_instance.delete()

        # Go through the complete list of the orchestrator, in order to add and/or modify deployments
        for deployment in deployments:
            # Check if blueprint exists in apps data model
            queryset = AppInstance.objects.all().filter(name=deployment['name'])

            if len(queryset) == 0:
                # If not, create an appInstance from the deployment and save it in the model
                # create deployment on database
                # create user in user model if it does not exist
                synchronize_user_in_model(deployment["owner"])

                # Link with the corresponding blueprint
                # get associated app
                app = Application.getByName(deployment["blueprint"])
                deployment.update({"is_new": "True"})
                LOGGER.info("Add deployment: " + str(deployment))

                serializer = self.get_serializer(data=deployment)
                if serializer.is_valid():
                    serializer.save(app=app)
                    LOGGER.info("Application Instance added!")
                else:
                    LOGGER.info(str(serializer.errors))
            else:
                # Check if the deployment cannot be considered 'new' anymore (new < 10 days) or if it was updated
                actual_object = queryset[0]
                inclusion_date = actual_object.created
                update_date = actual_object.updated
                today_date = datetime.now(timezone.utc)
                is_change = False

                # Change status from new to not new?
                if actual_object.is_new and (inclusion_date + timedelta(days=10)) < today_date:
                    actual_object.is_new = False
                    is_change = True
                    LOGGER.info("Deployment not new anymore.")

                # Update fields if it was updated in the Cloudify instance
                if update_date < datetime.strptime(deployment["updated"], "%Y-%m-%dT%H:%M:%S.%f%z"):
                    actual_object.is_updated = True
                    actual_object.description = deployment["description"]
                    actual_object.updated = deployment["updated"]
                    is_change = True
                    LOGGER.info("Deployment updated.")

                # Update the deployment information in the model (if there are changes)
                if is_change:
                    actual_object.save()
                    LOGGER.info("Updated deployment info: " + actual_object.name)

    @action(detail=False)
    def reset(self, request, *args, **kwargs):
        AppInstance.objects.all().delete()
        return Response("App instances (Deployments) reset in database", status=status.HTTP_200_OK)


class DataCatalogueKeyViewSet(viewsets.ModelViewSet):
    queryset = DataCatalogueKey.objects.all()
    serializer_class = DataCatalogueKeySerializer
    permission_classes = [IsAuthenticated]


class ComputingInfrastructureViewSet(viewsets.ModelViewSet):
    queryset = ComputingInfrastructure.objects.all()
    serializer_class = ComputingInfrastructureSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # TODO validate definition
        # if 'wm_config' not in dict_def:
        #     error = '"wm_config" key not found in definition file'
        # elif infra_type == cls.HPC:
        #     if 'country_tz' not in dict_def['wm_config']:
        #         error = '"country_tz" key not found in definition file under "wm_config"'
        #     elif 'partitions' not in dict_def:
        #         error = '"partitions" key not found in definition file'
        #     elif not isinstance(dict_def['partitions'], List) \
        #             and dict_def['partitions'] != 'None':
        #         error = '"partitions" key does not define a list or "None" value'
        #     elif 'mpi_versions' not in dict_def:
        #         error = '"mpi_versions" key not found in definition file'
        #     elif not isinstance(dict_def['mpi_versions'], List) \
        #             and dict_def['mpi_versions'] != 'None':
        #         error = '"mpi_versions" key does not define a list or "None" value'
        #     elif 'singularity_versions' not in dict_def:
        #         error = '"singularity_versions" key not found in definition file'
        #     elif not isinstance(dict_def['singularity_versions'], List) \
        #             and dict_def['singularity_versions'] != 'None':
        #         error = '"singularity_versions" key does not define a list or "None" value'
        # elif infra_type == cls.OPENSTACK:
        #     if 'openstack_config' not in dict_def:
        #         error = '"openstack_config" key not found in definition file'
        #     elif not isinstance(dict_def['openstack_config'], Dict):
        #         error = '"openstack_config" key does not define a dictionary'
        #     elif 'openstack_flavors' not in dict_def:
        #         error = '"openstack_flavors" key not found in definition file'
        #     elif not isinstance(dict_def['openstack_flavors'], List) \
        #             and dict_def['openstack_flavors'] != 'None':
        #         error = '"openstack_flavors" key does not define a list or "None" value'
        #     elif 'openstack_images' not in dict_def:
        #         error = '"openstack_images" key not found in definition file'
        #     elif not isinstance(dict_def['openstack_images'], List) \
        #             and dict_def['openstack_images'] != 'None':
        #         error = '"openstack_images" key does not define a list or "None" value'
        #     elif 'openstack_networks' not in dict_def:
        #         error = '"openstack_networks" key not found in definition file'
        #     elif not isinstance(dict_def['openstack_networks'], List) \
        #             and dict_def['openstack_networks'] != 'None':
        #         error = '"openstack_networks" key does not define a list or "None" value'
        #     elif 'openstack_volumes' not in dict_def:
        #         error = '"openstack_volumes" key not found in definition file'
        #     elif not isinstance(dict_def['openstack_volumes'], List) \
        #             and dict_def['openstack_volumes'] != 'None':
        #         error = '"openstack_volumes" key does not define a list or "None" value'
        # elif infra_type == cls.EOSC:
        #     if 'eosc_config' not in dict_def:
        #         error = '"eosc_config" key not found in definition file'
        #     elif not isinstance(dict_def['eosc_config'], Dict):
        #         error = '"eosc_config" key does not define a dictionary'
        #     elif 'eosc_flavors' not in dict_def:
        #         error = '"eosc_flavors" key not found in definition file'
        #     elif not isinstance(dict_def['eosc_flavors'], List) \
        #             and dict_def['eosc_flavors'] != 'None':
        #         error = '"eosc_flavors" key does not define a list or "None" value'
        #     elif 'eosc_images' not in dict_def:
        #         error = '"eosc_images" key not found in definition file'
        #     elif not isinstance(dict_def['eosc_images'], List) \
        #             and dict_def['eosc_images'] != 'None':
        #         error = '"eosc_images" key does not define a list or "None" value'
        #     elif 'eosc_networks' not in dict_def:
        #         error = '"eosc_networks" key not found in definition file'
        #     elif not isinstance(dict_def['eosc_networks'], List) \
        #             and dict_def['eosc_networks'] != 'None':
        #         error = '"eosc_networks" key does not define a list or "None" value'
        #     elif 'eosc_volumes' not in dict_def:
        #         error = '"eosc_volumes" key not found in definition file'
        #     elif not isinstance(dict_def['eosc_volumes'], List) \
        #             and dict_def['eosc_volumes'] != 'None':
        #         error = '"eosc_volumes" key does not define a list or "None" value'
        # else:
        #     error = 'unsopported type: "'+infra_type+'"'

        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class ComputingInstanceViewSet(viewsets.ModelViewSet):
    queryset = ComputingInstance.objects.all()
    serializer_class = ComputingInstanceSerializer
    permission_classes = [IsAuthenticated]


class InstanceExecutionViewSet(viewsets.ModelViewSet):
    queryset = InstanceExecution.objects.all()
    serializer_class = InstanceExecutionSerializer
    permission_classes = [IsAuthenticated]  # TODO use roles

    def list(self, request, *args, **kwargs):
        LOGGER.info("Requesting the list of Executions...")

        auth_header = self.request.META.get('HTTP_AUTHORIZATION')
        user_token = auth_header.replace('Bearer ', '', 1)
        user_name = vault.get_user_info(user_token)
        LOGGER.info("User listing (and filter): " + user_name)

        # TODO We should get all the executions of existing deployments going through their events (sync)
        # Update the information for all the executions that are not already registered aas 'terminated'
        self.update_executions(user_name)

        # Filter results by name, status and date if filter available
        name_filter = self.request.query_params.get('name')
        LOGGER.info("Name filter: " + str(name_filter))
        status_filter = self.request.query_params.get('status')
        LOGGER.info("Status filter: " + str(status_filter))
        created_filter = self.request.query_params.get('created')
        LOGGER.info("Created filter: " + str(status_filter))

        execs = InstanceExecution.objects.all()
        if name_filter is not None:
            execs = execs.filter(instance__name__icontains=name_filter)
            LOGGER.info("Instance name filter. Number of executions to send: " + str(len(execs)))

        if status_filter is not None:
            execs = execs.filter(status__icontains=status_filter)
            LOGGER.info("Status filter. Number of executions to send: " + str(len(execs)))

        if created_filter is not None:
            execs = execs.filter(created__gte=datetime.strptime(created_filter, "%Y-%m-%dT%H:%M:%S.%f%z"))
            LOGGER.info("Date filter. Number of executions to send: " + str(len(execs)))

        # Filter by owner
        execs = execs.filter(owner=user_name)
        LOGGER.info("Owner filter. Number of executions to send: " + str(len(execs)))

        serializer = InstanceExecutionSerializer(execs, many=True)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        return Response(status=status.HTTP_403_FORBIDDEN)

    def retrieve(self, request, *args, **kwargs):
        LOGGER.info("Requesting details of an execution...")
        execution = self.get_object()

        # Retrieve the list of inputs of the blueprint
        inputs = cfy.list_deployment_inputs(execution.instance.deployment_id())
        LOGGER.info("Inputs used: " + str(inputs))

        # Retrieve current information about the execution
        exec_full_info = cfy.get_execution(execution.id)

        # Update execution object
        execution.status = exec_full_info['status']
        execution.execution_time = exec_full_info['execution_time']
        execution.current_task = exec_full_info['current_task']
        execution.progress = exec_full_info['progress']
        execution.num_errors = exec_full_info['num_errors']
        if exec_full_info['status'] == 'terminated' or exec_full_info['status'] == 'failed':
            execution.finished = exec_full_info['end_time']
        if exec_full_info['num_errors'] > 0:
            execution.has_errors = True
        execution.save()

        # Build the response with all the data
        complete_result = {}
        serializer = self.get_serializer(execution)
        complete_result = serializer.data
        # complete_result['inputs'] = json.dumps(inputs)
        complete_result['current_operation'] = exec_full_info['current_operation']
        complete_result['error_message'] = exec_full_info['error_message']
        LOGGER.info("Complete result: " + str(complete_result))

        return Response(complete_result)

    def update(self, request, *args, **kwargs):
        return Response(status=status.HTTP_403_FORBIDDEN)

    def partial_update(self, request, *args, **kwargs):
        return Response(status=status.HTTP_403_FORBIDDEN)

    def destroy(self, request, *args, **kwargs):
        return Response(status=status.HTTP_403_FORBIDDEN)

    def update_executions(self, owner_user):
        LOGGER.info("Updating the status of the executions...")

        # Take the full list of executions in the DDBB and update them one by one
        # Executions cannot be deleted at Cloudify, so we go through all of them
        all_executions = InstanceExecution.objects.filter(owner=owner_user)
        for execution in all_executions:
            if execution.status != 'terminated':
                exec_full_info = cfy.get_execution(execution.id)
                LOGGER.info("Execution Info: " + str(exec_full_info))

                # Update progress, task, status, time...
                execution.status = exec_full_info['status']
                execution.execution_time = exec_full_info['execution_time']
                execution.current_task = exec_full_info['current_task']
                execution.progress = exec_full_info['progress']
                execution.num_errors = exec_full_info['num_errors']
                if exec_full_info['status'] == 'terminated' or exec_full_info['status'] == 'failed':
                    execution.finished = exec_full_info['end_time']
                if exec_full_info['num_errors'] > 0:
                    execution.has_errors = True
                execution.save()


class UserCredentialsViewSet(APIView):
    permission_classes = [IsAuthenticated]  # TODO use roles

    def get(self, request):
        # Retrieve user's token to check in Keycloak
        auth_header = self.request.META.get('HTTP_AUTHORIZATION')
        user_token = auth_header.replace('Bearer ', '', 1)
        LOGGER.info("Security token: " + str(user_token))
        token_info = vault.get_user_info(user_token)
        LOGGER.info("User name: " + token_info)

        # List all the credentials stored for the user with the token
        vault_credentials = vault.get_user_tokens(user_token)

        return Response(vault_credentials)

    def post(self, request, format=None):
        # Retrieve user's token to check in Keycloak
        auth_header = self.request.META.get('HTTP_AUTHORIZATION')
        user_token = auth_header.replace('Bearer ', '', 1)
        LOGGER.info("Security token credential: " + str(user_token))
        token_info = vault.get_user_info(user_token)
        LOGGER.info("User name: " + token_info)
        credential_data = request.data
        LOGGER.info("New credential data host: " + credential_data["host"])

        # List all the credentials stored for the user with the token
        vault_upload = vault.upload_user_secret(user_token, credential_data)

        return Response(vault_upload)


class CredentialViewSet(APIView):
    permission_classes = [IsAuthenticated]  # TODO use roles

    def get(self, request, pk, format=None):
        # Retrieve user's token to check in Keycloak
        auth_header = self.request.META.get('HTTP_AUTHORIZATION')
        user_token = auth_header.replace('Bearer ', '', 1)
        LOGGER.info("Security token credential: " + str(user_token))
        token_info = vault.get_user_info(user_token)
        LOGGER.info("User name: " + token_info)
        LOGGER.info("Credential Id: " + pk)

        # List all the credentials stored for the user with the token
        # vault_credential = vault.get_user_token_info(user_token, pk)

        return Response(token_info)

    def delete(self, request, pk, format=None):
        # Retrieve user's token to check in Keycloak
        auth_header = self.request.META.get('HTTP_AUTHORIZATION')
        user_token = auth_header.replace('Bearer ', '', 1)
        LOGGER.info("Security token credential: " + str(user_token))
        token_info = vault.get_user_info(user_token)
        LOGGER.info("User name: " + token_info)
        LOGGER.info("Credential Id: " + pk)

        # List all the credentials stored for the user with the token
        # vault_delete = vault.remove_user_secret(user_token, pk)

        return Response(token_info)


class CKANViewSet(APIView):
    permission_classes = [IsAuthenticated]  # TODO use roles

    def get(self, request, format=None):
        # Prepare the CKAN endpoint
        CKAN_endpoint = "https://ckan.hidalgo-project.eu/api/3/action/package_search"
        ckan_filter = self.request.query_params.get('keywords')
        ckan_payload = {'q': ckan_filter}
        response = get(CKAN_endpoint, params=ckan_payload)
        ckan_response = response.json()

        results_list = ckan_response["result"]["results"]
        LOGGER.info("CKAN Results: " + str(results_list))

        ckan_result_list = [
            {
                "name": dataset["name"],
                "dataset_id": dataset["id"],
            }
            for dataset in results_list
        ]
        LOGGER.info("CKAN Results: " + str(ckan_result_list))

        return Response(ckan_result_list)
