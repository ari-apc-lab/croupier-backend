import json
import tempfile
# import pdb
import yaml
import logging

from django.http import JsonResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from django.contrib.auth.models import User

from croupier import cfy
from croupier.models import (
    Application,
    AppInstance,
    DataCatalogueKey,
    ComputingInfrastructure,
    ComputingInstance,
)
from croupier.serializers import (
    ApplicationSerializer,
    AppInstanceSerializer,
    DataCatalogueKeySerializer,
    ComputingInfrastructureSerializer,
    ComputingInstanceSerializer,
)

# Get an instance of a logger
LOGGER = logging.getLogger(__name__)


def serializeBlueprintList(blueprints):
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
    return data


def serializeDeploymentList(deployments):
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


def synchronizeUserInModel(username):
    # Check if user exist, if not create it
    queryset = User.objects.all().filter(username=username)
    if len(queryset) == 0:
        user = User.objects.create_user(username=username,
                                        email='not given',
                                        password=username)


class ApplicationViewSet(viewsets.ModelViewSet):
    queryset = Application.objects.all()
    serializer_class = ApplicationSerializer
    permission_classes = [IsAuthenticated]  # TODO use roles

    def list(self, request, *args, **kwargs):
        LOGGER.info("Requesting the list of Applications")
        blueprints = cfy.list_blueprints()
        # Synchronize blueprints returned from Cloudify with the internal model database of apps
        # For each returned blueprint, check if the blueprint exits in the internal database by name
        # If not, create the app and store it in the database
        # Rational: blueprints could be uploaded in Cloudify using its console, not necessarily using
        # the Hidalgo frontend
        data = serializeBlueprintList(blueprints[0])
        self.synchronizeBlueprintListInModel(data)
        apps = Application.objects.all()
        serializer = ApplicationSerializer(apps, many=True)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        # Request is immutable by default
        _mutable = request.data._mutable
        request.data._mutable = True
        request.data["owner"] = request.user.username
        request.data._mutable = _mutable
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # create blueprint in cloudify
        blueprint_package = request.data["blueprint"]

        tmp_package_file = tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False)
        for chunk in blueprint_package.chunks():
            tmp_package_file.write(chunk)
        tmp_package_file.flush()

        path = tmp_package_file.name
        blueprint_id = Application.create_blueprint_id(request.data["name"])
        _, err = cfy.upload_blueprint(path, blueprint_id)

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
        instance = self.get_object()
        serializer = self.get_serializer(instance)

        # add inputs to instance data
        inputs = cfy.list_blueprint_inputs(instance.blueprint_id())
        serializer.data["inputs"] = json.dumps(inputs)

        return Response(serializer.data)

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

    def synchronizeBlueprintListInModel(self, blueprints):
        for blueprint in blueprints:
            # Check if blueprint exists in apps data model
            queryset = Application.objects.all().filter(name=blueprint['name'])
            if len(queryset) == 0:
                # If not, create an app from the blueprint and save it in the model
                # create blueprint on database
                # create user in user model if it does not exist
                synchronizeUserInModel(blueprint["owner"])
                serializer = self.get_serializer(data=blueprint)
                if serializer.is_valid():
                    self.perform_create(serializer)


class AppInstanceViewSet(viewsets.ModelViewSet):
    queryset = AppInstance.objects.all()
    serializer_class = AppInstanceSerializer
    permission_classes = [IsAuthenticated]

    def list(self, request, *args, **kwargs):
        LOGGER.info("Requesting the list of Instances")
        deployments = cfy.list_deployments()
        # Synchronize deployments returned from Cloudify with the internal model database of application instances
        # For each returned deployment, check if the deployment exits in the internal database by name
        # If not, create the app and store it in the database
        # Rational: deployments could be created in Cloudify using its console, not necessarily using
        # the Hidalgo frontend
        data = serializeDeploymentList(deployments[0])
        self.synchronizeDeploymentListInModel(data)
        instances = AppInstance.objects.all()
        serializer = AppInstanceSerializer(instances, many=True)
        return Response(serializer.data)

    def get_queryset(self):
        user = self.request.user
        return AppInstance.objects.filter(owner=user)

    def create(self, request, *args, **kwargs):
        request.data["owner"] = request.user

        blueprint_id = Application.create_blueprint_id(request.data["app"])
        deployment_id = AppInstance.create_deployment_id(request.data["name"])
        # create deployment in cloudify
        tmp_package_file = tempfile.NamedTemporaryFile(suffix=".yaml", delete=False)
        for chunk in request.data["inputs_file"].chunks():
            tmp_package_file.write(chunk)
        tmp_package_file.flush()

        path = tmp_package_file.name
        inputs = None
        with open(path) as file:
            inputs = yaml.load(file, Loader=yaml.FullLoader)

        _, err = cfy.create_deployment(
            blueprint_id, deployment_id, inputs
        )

        if err:
            return Response(err, status=status.HTTP_409_CONFLICT)

        # execute install workflow
        execution, err = cfy.execute_workflow(deployment_id, cfy.INSTALL)

        if err:
            return Response(err, status=status.HTTP_409_CONFLICT)

        request.data._mutable = True
        request.data["last_execution"] = execution["id"]
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # create deployment on database. If it were to fail, reverse the process on Cloudify
        try:
            self.perform_create(serializer)
        except Exception:
            cfy.execute_workflow(deployment_id, cfy.UNINSTALL)
            cfy.destroy_deployment(deployment_id)
            return Response(err, status=status.HTTP_409_CONFLICT)
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()

        if instance.owner != request.user:
            return Response(status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(instance)

        # add inputs to instance data
        inputs = cfy.list_deployment_inputs(instance.deployment_id())
        serializer.data["inputs"] = json.dumps(inputs)

        return Response(serializer.data)

    def update(self, request, *args, **kwargs):
        return Response(status=status.HTTP_403_FORBIDDEN)

    def partial_update(self, request, *args, **kwargs):
        return Response(status=status.HTTP_403_FORBIDDEN)

    @action(methods=["post"], detail=True)
    def execute(self, request, pk=None):
        instance = self.get_object()

        if instance.owner != request.user:
            return Response(status=status.HTTP_403_FORBIDDEN)

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
        return Response(serializer.data)

    @action(detail=True)
    def events(self, request, pk=None):
        instance = self.get_object()

        if instance.owner != request.user:
            return Response(status=status.HTTP_403_FORBIDDEN)

        offset = request.data["offset"]

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

    def synchronizeDeploymentListInModel(self, deployments):
        for deployment in deployments:
            # Check if deployment exists in apps data model
            queryset = AppInstance.objects.all().filter(name=deployment['name'])
            if len(queryset) == 0:
                # If not, create an app from the deployment and save it in the model
                # create deployment on database
                # create user in user model if it does not exist
                synchronizeUserInModel(deployment["owner"])
                # get associated app
                app = Application.getByName(deployment["blueprint"])
                serializer = self.get_serializer(data=deployment)
                if serializer.is_valid():
                    serializer.save(app=app)


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
