#!/bin/bash
set -e

yay -S miniconda3 --noconfirm
sudo ln -s /opt/miniconda3/etc/profile.d/conda.sh /etc/profile.d/conda.sh
source /opt/miniconda3/etc/profile.d/conda.sh
conda create -y -n hidalgo-api python=3.7
conda init bash
conda config --set auto_activate_base False
conda activate hidalgo-api
pip install Django==2.2.3
pip install djangorestframework==3.10.0
pip install mozilla-django-oidc==1.2.2

