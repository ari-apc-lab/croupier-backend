from rest_framework import serializers

from croupier.models import (
    Application,
    AppInstance,
    # ComputingInfrastructure,
    # ComputingInstance,
    # DataCatalogueKey,
)


class ApplicationSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Application
        fields = ["name", "description", "owner"]


class AppInstanceSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = AppInstance
        fields = ["name", "description", "owner", "app", "last_execution"]
