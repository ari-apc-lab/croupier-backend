#!/bin/bash
set -e

#yay -S miniconda3 --noconfirm
#sudo ln -s /opt/miniconda3/etc/profile.d/conda.sh /etc/profile.d/conda.sh
#source /opt/miniconda3/etc/profile.d/conda.sh
#conda create -y -n hidalgo-api python=3.7
#conda init bash
#conda config --set auto_activate_base False
#conda activate hidalgo-api
pip install Django==2.2.3
pip install djangorestframework==3.10.0
pip install mozilla-django-oidc==1.2.2
#pip install cloudify-rest-client==4.3.1
pip install django-cors-headers
pip install uwsgi
# Hack to be python3 compatible
#PYPKG=$(python -c "import sys; print(sys.path[-1])")
PYPKG=venv/lib/python3.6/site-packages
sed -i 's/import urlparse/#import urlparse/g' $PYPKG/cloudify_rest_client/*.py
sed -i 's/urlparse\./urllib.parse./g' $PYPKG/cloudify_rest_client/*.py
sed -i 's/urllib\.quote/urllib.parse.quote/g' $PYPKG/cloudify_rest_client/*.py

sed -i 's/import urlparse/#import urlparse/g' $PYPKG/cloudify_rest_client/aria/*.py
sed -i 's/urlparse\./urllib.parse./g' $PYPKG/cloudify_rest_client/aria/*.py
sed -i 's/urllib\.quote/urllib.parse.quote/g' $PYPKG/cloudify_rest_client/aria/*.py

sed -i 's/urlsafe_b64encode(credentials)/urlsafe_b64encode(credentials.encode("utf-8"))/g' $PYPKG/cloudify_rest_client/client.py
sed -i 's/+ encoded_credentials/+ str(encoded_credentials, "utf-8")/g' $PYPKG/cloudify_rest_client/client.py
sed -i '/self.response = response/a\        self.message = message' $PYPKG/cloudify_rest_client/exceptions.py
