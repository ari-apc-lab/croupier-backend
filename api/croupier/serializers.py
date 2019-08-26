from rest_framework import serializers

from croupier.models import (
    Application,
    AppInstance,
    # ComputingInfrastructure,
    # ComputingInstance,
    # DataCatalogueKey,
)


class ApplicationSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Application
        fields = ["name", "description", "owner"]


class AppInstanceSerializer(serializers.HyperlinkedModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(read_only=True)
    app = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = AppInstance
        fields = ["name", "description", "owner", "app", "last_execution"]
