""" Application models """

import logging
from django.conf import settings
from django.db import models

# from .common import (
#     backend,
#     _to_dict,
#     get_inputs_list,
#     delete_secrets,
#     NAME_TAG,
#     ORDER_TAG,
# )

# Get an instance of a logger
LOGGER = logging.getLogger(__name__)


class Application(models.Model):
    name = models.CharField(max_length=50, unique=True)
    description = models.CharField(max_length=256, null=True)
    main_blueprint_file = models.CharField(max_length=50, unique=False)
    created = models.DateTimeField()
    included = models.DateTimeField()
    updated = models.DateTimeField()
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, to_field='username')
    is_new = models.BooleanField(default=False)
    is_updated = models.BooleanField(default=False)
    is_advertised = models.BooleanField(default=False)

    @classmethod
    def create_blueprint_id(cls, name):
        return "_".join(name.lower().split())

    @classmethod
    def getByName(cls, name):
        return Application.objects.all().filter(name=name)[0]

    def blueprint_id(self):
        return Application.create_blueprint_id(self.name)

    def __str__(self):
        return "Application {0} from {1}".format(self.name, self.owner.username)


class AppInstance(models.Model):
    name = models.CharField(max_length=50, unique=True)
    description = models.CharField(max_length=256, null=True)
    created = models.DateTimeField()
    updated = models.DateTimeField()
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, to_field='username')
    # inputs = models.TextField(null=True)

    app = models.ForeignKey(Application, on_delete=models.CASCADE)
    last_execution = models.CharField(max_length=50, null=True)
    is_new = models.BooleanField(default=False)

    @classmethod
    def create_deployment_id(cls, name):
        return "_".join(name.lower().split())

    @classmethod
    def getByName(cls, name):
        return AppInstance.objects.all().filter(name=name)[0]

    def deployment_id(self):
        return self.name


class DataCatalogueKey(models.Model):
    """ Data catalogue key model """

    code = models.CharField(max_length=50)

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    def __str__(self):
        return "Key from {0}".format(self.owner.username)


class ComputingInfrastructure(models.Model):
    """ General Infrastructure settings """

    name = models.CharField(max_length=50, unique=True)
    about_url = models.CharField(max_length=250)

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    HPC = "HPC"
    OPENSTACK = "OPENSTACK"
    EOSC = "EOSC"
    TYPE_CHOICES = ((HPC, "HPC"), (OPENSTACK, "OpenStack"), (EOSC, "EOSC-Hub"))
    infra_type = models.CharField(max_length=10, choices=TYPE_CHOICES)

    SLURM = "SLURM"
    TORQUE = "TORQUE"
    BASH = "BASH"
    INTERFACE_CHOICES = ((SLURM, "Slurm"), (TORQUE, "Torque"), (BASH, "Bash"))
    interface = models.CharField(max_length=6, choices=INTERFACE_CHOICES)

    definition = models.TextField()


class ComputingInstance(models.Model):
    """ User's Infrastructure """

    name = models.CharField(max_length=50)

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    infrastructure = models.ForeignKey(
        ComputingInfrastructure, on_delete=models.CASCADE, null=False
    )

    definition = models.TextField()


class InstanceExecution(models.Model):
    # Basic info (id provided by Cloudify and deployment linked to the execution
    id = models.CharField(max_length=50, unique=True, primary_key=True)
    instance = models.ForeignKey(AppInstance, on_delete=models.CASCADE)

    # Time-related properties
    created = models.DateTimeField()
    finished = models.DateTimeField(null=True)
    execution_time = models.IntegerField(null=True)

    # User who created the execution
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, to_field='username')

    # Properties related to the status
    PENDING = "PENDING"
    STARTED = "STARTED"
    CANCELLING = "CANCELLING"
    FORCE_CANCELLING = "FORCE_CANCELLING"
    CANCELLED = "CANCELLED"
    TERMINATED = "TERMINATED"
    FAILED = "FAILED"
    QUEUED = "QUEUED"
    SCHEDULED = "SCHEDULED"
    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (STARTED, 'Started'),
        (CANCELLING, 'Cancelling'),
        (FORCE_CANCELLING, 'Force Cancelling'),
        (CANCELLED, 'Cancelled'),
        (TERMINATED, 'Terminated'),
        (FAILED, 'Failed'),
        (QUEUED, 'Queued'),
        (SCHEDULED, 'Scheduled'),
    ]
    status = models.CharField(max_length=17, choices=STATUS_CHOICES, default=PENDING)
    has_errors = models.BooleanField(default=False)
    num_errors = models.IntegerField(default=0)
    current_task = models.CharField(max_length=50, null=True)
    progress = models.FloatField(default=0.0)

    @classmethod
    def getByName(cls, name):
        return InstanceExecution.objects.all().filter(id=name)[0]

