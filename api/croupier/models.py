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
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, to_field='username')

    @classmethod
    def create_blueprint_id(cls, name):
        return "_".join(name.lower().split())

    def blueprint_id(self):
        return Application.create_blueprint_id(self.name)

    def __str__(self):
        return "Application {0} from {1}".format(self.name, self.owner.username)


class AppInstance(models.Model):
    name = models.CharField(max_length=50, unique=True)
    description = models.CharField(max_length=256, null=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    # inputs = models.TextField(null=True)

    app = models.ForeignKey(Application, on_delete=models.CASCADE)
    last_execution = models.CharField(max_length=50)


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
    interface = models.CharField(max_length=5, choices=INTERFACE_CHOICES)

    definition = models.TextField()


class ComputingInstance(models.Model):
    """ User's Infrastructure """

    name = models.CharField(max_length=50)

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    infrastructure = models.ForeignKey(
        ComputingInfrastructure, on_delete=models.CASCADE, null=False
    )

    definition = models.TextField()
