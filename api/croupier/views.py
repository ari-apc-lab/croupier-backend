from django.shortcuts import render
from rest_framework import serializers
from rest_framework import viewsets
from rest_framework.response import Response


class Task:
    def __init__(self, **kwargs):
        for field in ("id", "name", "owner", "status"):
            setattr(self, field, kwargs.get(field, None))


tasks = {
    1: Task(id=1, name="Demo", owner="xordoquy", status="Done"),
    2: Task(id=2, name="Model less demo", owner="xordoquy", status="Ongoing"),
    3: Task(id=3, name="Sleep more", owner="xordoquy", status="New"),
}

STATUSES = ["Done", "Ongoing", "New"]


class TaskSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(max_length=256)
    owner = serializers.CharField(max_length=256)
    status = serializers.ChoiceField(choices=STATUSES, default="New")

    def create(self, validated_data):
        return Task(id=None, **validated_data)

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        return instance


class TaskViewSet(viewsets.ViewSet):
    # Required for the Browsable API renderer to have a nice form.
    serializer_class = TaskSerializer

    def list(self, request):
        serializer = TaskSerializer(instance=tasks.values(), many=True)
        return Response(serializer.data)

