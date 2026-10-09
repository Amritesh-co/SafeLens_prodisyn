#!/bin/bash
cd /home/ubuntu/safelensai-backend/safelensai-backend-api-server
 
echo "Setting up virtual environment"
 
python3 -m venv venv
source venv/bin/activate
 
echo "Installing dependencies"
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt

#gave permissions in ec2