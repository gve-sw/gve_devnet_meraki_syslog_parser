#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Copyright (c) 2020 Cisco and/or its affiliates.
This software is licensed to you under the terms of the Cisco Sample
Code License, Version 1.1 (the "License"). You may obtain a copy of the
License at
               https://developer.cisco.com/docs/licenses
All use of the material herein must be in accordance with the terms of
the License. All rights not expressly granted by the License are
reserved. Unless required by applicable law or agreed to separately in
writing, software distributed under the License is distributed on an "AS
IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
or implied.
"""

__author__ = "Josh Ingeniero <jingenie@cisco.com>"
__copyright__ = "Copyright (c) 2020 Cisco and/or its affiliates."
__license__ = "Cisco Sample Code License, Version 1.1"

# Meraki Details
API_KEY = "API_KEY"
NETWORK_ID = "NETWORK_ID"

# Syslog Server Details
ADDRESS = '127.0.0.1'
PORT = 514

# Best to keep LOOKBACK * 2 INTERVAL or higher
LOOKBACK = 20
INTERVAL = LOOKBACK / 2
import logging
import meraki
import logging.handlers

from tinydb import TinyDB
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.schedulers.background import BackgroundScheduler

SCHEMA = {
    "timestamp": "",
    "type": "8021x_auth",
    "ssid": "",
    "gateway_device_mac": "",
    "client_mac": "",
    "last_known_client_ip": "",
    "identity": ""
}

sched = BlockingScheduler()
sending = BackgroundScheduler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('MyLogger')
logger.setLevel(logging.DEBUG)
handler = logging.handlers.SysLogHandler(address=(ADDRESS, PORT))
dashboard = meraki.DashboardAPI(api_key=API_KEY, suppress_logging=True)
logger.addHandler(handler)
db = TinyDB('db.json')


def setup_logger(name, log_file, level=logging.DEBUG):
    """To setup as many loggers as you want"""

    # handler = logging.FileHandler(log_file, mode='a')
    handler = logging.handlers.RotatingFileHandler(log_file, mode='a', maxBytes=100000000, backupCount=10)
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)

    return logger


def check_splash_login():
    response = dashboard.networks.getNetworkSplashLoginAttempts(
        networkId=NETWORK_ID,
        timespan=LOOKBACK,
        total_pages="all"
    )
    response[:] = [d for d in response if d.get('authorization') != 'failure']  # Remove failed logins
    return response


def store_splash_response(data):
    for item in data:
        db.insert(item)


def prune_data(new_data):
    old_data = db.all()
    pruned_data = [x for x in new_data if x not in old_data]
    return pruned_data


def send_to_syslog(data):
    backlogger.info("Starting to send info")
    for item in data:
        ip = dashboard.networks.getNetworkClient(networkId=NETWORK_ID, clientId=item['clientId'])
        info_list = [f"""timestamp='{item["loginAt"]}'""", f"""type='8021x_auth'""", f"""ssid='{item["ssid"]}'""",
                     f"""gateway_device_mac='{item["gatewayDeviceMac"]}'""", f"""client_mac='{item["clientMac"]}'""",
                     f"""last_known_client_ip='{ip["ip"]}'""", f"""identity='asis0\\{item["login"]}'"""]
        separator = " "
        info_string = separator.join(info_list)
        logger.info(info_string)
        backlogger.info(f"Sent to Syslog: {info_string}")


def main():
    backlogger.info("Starting Splash Login to Syslog Script")
    current = check_splash_login()  # Check the current data for the past interval
    backlogger.debug(f"Current Payload: {current}")
    current_pruned = prune_data(current)  # Prunes the data of data previously collected
    if current_pruned:  # If pruned data exists, that means there is new data
        backlogger.debug(f"Pruned Payload: {current}")
        db.truncate()  # Remove old entries
        store_splash_response(current_pruned)  # Store new entries
        sending.add_job(send_to_syslog, args=[current_pruned])  # Add new job to send syslog asynchronously
    else:  # No new data
        backlogger.debug('Current Payload matches previous or empty')


if __name__ == '__main__':
    backlogger = setup_logger('backendLog', 'app.log')  # Back end logger
    setup_logger('apscheduler', 'app.log')  # apscheduler job logs
    sending.start()  # start thread for syslog send queue
    sched.add_job(main, trigger='interval', seconds=INTERVAL)  # main thread to query meraki
    sched.start()
