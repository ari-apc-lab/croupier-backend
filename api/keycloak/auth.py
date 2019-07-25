from mozilla_django_oidc.auth import OIDCAuthenticationBackend


class OIDCAuthBackend(OIDCAuthenticationBackend):
    def get_userinfo(self, access_token, id_token, payload):
        """Return user details dictionary (keycloak user info + access token info).
        The id_token and payload are not used in this implementation """
        user_info = super().get_userinfo(access_token, id_token, payload)
        payload = self.verify_token(id_token)

        return {**user_info, **payload}

    def update_user(self, user, claims):
        """Update existing user with new claims, if necessary save, and return user"""
        # TODO update with claims
        # user.[] = []
        # user.save()
        return user

    def create_user(self, claims):
        """Return object for a newly created user account."""
        email = claims.get("email")
        username = self.get_username(claims)
        # TODO add other user information like roles?
        return self.UserModel.objects.create_user(username, email)

    def tokenExchange(self, token):
        """Return new token from backend client"""
        # TODO
        return ""
