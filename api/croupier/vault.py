""" Vault python wrapper """
from base64 import b64encode
from os import getenv
from requests import post, Session, adapters, get, delete
from requests import request
import json

import logging

# Get an instance of a logger
LOGGER = logging.getLogger(__name__)

# General variables
oidc_client_id = getenv("OIDC_RP_CLIENT_ID", "backend")
oidc_client_secret = getenv("OIDC_RP_CLIENT_SECRET", "")
oidc_introspection_endpoint = getenv("OIDC_OP_TOKEN_ENDPOINT", "") + "/introspect"
vault_endpoint = getenv("VAULT_ADDRESS", "") + ":" + getenv("VAULT_PORT", "8200")
if not vault_endpoint.startswith('http'):
    vault_endpoint = 'http://' + vault_endpoint
vault_admin_token = getenv("VAULT_ADMIN_TOKEN", "")


def get_user_info(access_token):
    token_info = _token_info(access_token)
    LOGGER.info("Security token info: " + str(token_info))
    user_name = token_info["preferred_username"]
    return user_name


def get_user_tokens(access_token):
    # Connect with the Vault_Secret_Uploader to get all the secrets
    # Prepare headers (authentication)
    vault_headers = {'Authorization': 'Bearer ' + access_token}

    # Send request and get secrets
    response = get(vault_endpoint, headers=vault_headers)
    credentials_list = response.json()
    LOGGER.info("Vault secrets: " + str(credentials_list))
    return credentials_list


def upload_user_secret(access_token, credentials_dic):
    # Connect with the Vault_Secret_Uploader to get all the secrets
    # Prepare headers (authentication)
    vault_headers = {'Authorization': 'Bearer ' + access_token}

    # Send request and get secrets
    response = post(vault_endpoint, headers=vault_headers, data=credentials_dic)
    upload_response = response.json()
    LOGGER.info("Vault response: " + str(upload_response))
    return upload_response


def _token_info(access_token) -> dict:
    req = {'token': access_token}
    headers = {'Content-type': 'application/x-www-form-urlencoded'}
    if not oidc_introspection_endpoint:
        raise Exception("No oidc_introspection_endpoint set on the server\n")

    basic_auth_string = '{0}:{1}'.format(oidc_client_id, oidc_client_secret)
    basic_auth_bytes = bytearray(basic_auth_string, 'utf-8')
    headers['Authorization'] = 'Basic {0}'.format(b64encode(basic_auth_bytes).decode('utf-8'))

    token_response = post(oidc_introspection_endpoint, data=req, headers=headers)
    if not token_response.ok:
        raise Exception("There was a problem trying to authenticate with keycloak:\n"
                        " HTTP code: " + str(token_response.status_code) + "\n"
                        " Content:" + str(token_response.content) + "\n")

    json_response = token_response.json()
    if "active" in json_response and json_response["active"] is False:
        return {}
    return json_response
