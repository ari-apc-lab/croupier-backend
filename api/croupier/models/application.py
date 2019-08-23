""" Application models """

import logging

from django.conf import settings

from django.db import models  # , connection, IntegrityError


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
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    @classmethod
    def create_blueprint_id(cls, name):
        return name.lower().split().join("_")

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
