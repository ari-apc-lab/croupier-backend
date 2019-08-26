from rest_framework import serializers

from croupier.models import (
    Application,
    AppInstance,
    ComputingInfrastructure,
    ComputingInstance,
    DataCatalogueKey,
)


class ApplicationSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Application
        fields = ["name", "description", "owner"]


class AppInstanceSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(read_only=True)
    app = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = AppInstance
        fields = ["name", "description", "owner", "app", "last_execution"]


class DataCatalogueKeySerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = DataCatalogueKey
        fields = ["code", "owner"]


class ComputingInfrastructureSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = ComputingInfrastructure
        fields = ["name", "about_url", "owner", "infra_type", "interface", "definition"]


class ComputingInstanceSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(read_only=True)
    infrastructure = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = ComputingInstance
        fields = ["name", "owner", "infrastructure", "definition"]
