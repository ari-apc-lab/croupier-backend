"""api URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from django.conf.urls import url, include

from croupier import views

urlpatterns = [
    path("admin/", admin.site.urls),
#    url(r"^oidc/", include("mozilla_django_oidc.urls")),
    path("api-auth/", include("rest_framework.urls", namespace="rest_framework")),
    path("oidc/", include("mozilla_django_oidc.urls")),
    path("", include("croupier.urls")),
    path("credentials/", views.UserCredentialsViewSet.as_view()),
    path("credentials/<str:pk>/", views.CredentialViewSet.as_view()),
    path("ckan/", views.CKANViewSet.as_view())
]
