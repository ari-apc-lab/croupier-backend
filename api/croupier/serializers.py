from rest_framework import serializers
from django.contrib.auth.models import User

from croupier.models import (
    Application,
    AppInstance,
    InstanceExecution,
    ComputingInfrastructure,
    ComputingInstance,
    DataCatalogueKey,
)


class ApplicationSerializer(serializers.ModelSerializer):
    owner = serializers.SlugRelatedField(slug_field="username", queryset=User.objects.all())

    class Meta:
        model = Application
        fields = ["id", "name", "description", "owner", "main_blueprint_file", "created", "included", "updated",
                  "is_new", "is_updated", "is_advertised"]


class AppInstanceSerializer(serializers.ModelSerializer):
    owner = serializers.SlugRelatedField(slug_field="username", queryset=User.objects.all())
    app = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = AppInstance
        fields = ["id", "name", "description", "owner", "created", "updated", "app", "last_execution", "is_new"]


class DataCatalogueKeySerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = DataCatalogueKey
        fields = ["id", "code", "owner"]


class ComputingInfrastructureSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = ComputingInfrastructure
        fields = [
            "id",
            "name",
            "about_url",
            "owner",
            "infra_type",
            "interface",
            "definition",
        ]


class ComputingInstanceSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(read_only=True)
    infrastructure = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = ComputingInstance
        fields = ["id", "name", "owner", "infrastructure", "definition"]


class InstanceExecutionSerializer(serializers.ModelSerializer):
    owner = serializers.SlugRelatedField(slug_field="username", queryset=User.objects.all())
    instance = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = InstanceExecution
        fields = [
            "id",
            "instance",
            "created",
            "finished",
            "execution_time",
            "owner",
            "status",
            "has_errors",
            "num_errors",
            "current_task",
            "progress"
        ]

