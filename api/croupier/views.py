import json
import tempfile

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from croupier import cfy
from croupier.models import (
    Application,
    AppInstance,
    # ComputingInfrastructure,
    # ComputingInstance,
    # DataCatalogueKey,
)
from croupier.serializers import ApplicationSerializer, AppInstanceSerializer


class ApplicationViewSet(viewsets.ModelViewSet):
    queryset = Application.objects.all()
    serializer_class = ApplicationSerializer
    permission_classes = [IsAuthenticated]  # TODO use roles

    def create(self, request, *args, **kwargs):
        request.data["owner"] = request.user.username
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # create blueprint in cloudify
        blueprint_package = request.data["blueprint_package"]

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
        if err:
            return Response(err, status=status.HTTP_409_CONFLICT)

        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AppInstanceViewSet(viewsets.ModelViewSet):
    queryset = AppInstance.objects.all()
    serializer_class = AppInstanceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return AppInstance.objects.filter(owner=user)

    def create(self, request, *args, **kwargs):
        request.data["owner"] = request.user
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        blueprint_id = Application.create_blueprint_id(request.data["app"])
        deployment_id = AppInstance.create_deployment_id(request.data["name"])
        # create deployment in cloudify
        _, err = cfy.create_deployment(
            deployment_id, blueprint_id, request.data["inputs"]
        )

        if err:
            return Response(err, status=status.HTTP_409_CONFLICT)

        # execute install workflow
        execution, err = cfy.execute_workflow(deployment_id, cfy.INSTALL)

        if err:
            return Response(err, status=status.HTTP_409_CONFLICT)

        serializer.data["last_execution"] = execution["id"]

        # create deployment on database
        self.perform_create(serializer)
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

    @action(methods=["post"], detail=True)
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
