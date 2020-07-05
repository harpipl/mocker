import os
import random
import time
import uuid
from datetime import datetime

import pandas as pd
import requests
from flask import Flask, request
from waitress import serve

app = Flask(__name__)


class Route:
    def __init__(self, name, path, method, req_format, status, delay, forwarded, strategy, response_path):
        self.name = name
        self.path = path
        self.method = method
        self.format = req_format
        self.status = status
        self.delay = delay
        self.forwarded = forwarded
        self.strategy = strategy
        self.response_path = response_path
        self.selected_file = -1
        self.files = {}


ROUTES = {}


def sleep(delay):
    if delay > 0:
        time.sleep(delay)


def status_unknown():
    return 'UNKNOWN'


def read_from_file(path, formats):
    fin = open(path, 'rb')
    response = fin.read().decode('utf-8')
    fin.close()

    return response, {'Content-Type': 'application/xml; charset=utf-8'}


def status_mocked_and_strategy_concrete(route):
    return read_from_file(route.path, route.format)


def status_mocked_and_strategy_random(route):
    return read_from_file(route.files[random.randint(0, len(route.files) - 1)], route.format)


def status_mocked_and_strategy_sequence(route):
    route.selected_file = (route.selected_file + 1) % len(route.files)
    return read_from_file(route.files[route.selected_file], route.format)


def status_mocked(route):
    if route.strategy == 'CONCRETE':
        return status_mocked_and_strategy_concrete(route)
    elif route.strategy == 'RANDOM':
        return status_mocked_and_strategy_random(route)
    elif route.strategy == 'SEQUENCE':
        return status_mocked_and_strategy_sequence(route)

    return status_unknown()


def status_forwarded(route):
    if route.method == 'GET':
        resp = requests.get(route.forwarded, data=request.data)
    elif route.method == 'POST':
        resp = requests.post(route.forwarded, data=request.data)
    elif route.method == 'PUT':
        resp = requests.put(route.forwarded, data=request.data)
    elif route.method == 'HEAD':
        resp = requests.head(route.forwarded, data=request.data)
    elif route.method == 'DELETE':
        resp = requests.delete(route.forwarded, data=request.data)
    elif route.method == 'OPTIONS':
        resp = requests.options(route.forwarded, data=request.data)
    else:
        resp = requests.patch(route.forwarded, data=request.data)

    return resp


def status_recording(route):
    now = datetime.now()
    key = now.strftime("%Y%m%d_%H%M%S_%f") + "_" + str(uuid.uuid1())

    fin = open(route.response_path + os.path.sep + key + "_req.dat", "wb")
    fin.write(request.data)

    resp = status_forwarded(route)

    fout = open(route.response_path + os.path.sep + key + "_res.dat", "wb")
    fout.write(resp.text.encode("utf-8"))

    fin.close()
    fout.close()

    return resp.text, {'Content-Type': 'application/xml; charset=utf-8'}


def callback():
    route = ROUTES['[' + request.method + ']' + request.path]

    sleep(route.delay)

    if route.status == 'MOCKED':
        return status_mocked(route)
    elif route.status == 'FORWARDED':
        return status_forwarded(route)
    elif route.status == 'RECORDING':
        return status_recording(route)
    else:
        return status_unknown()


def add_route(name, path, method, req_format, status, delay, forwarded, strategy, response_path):
    if status is not None and status != 'DISABLED':
        ROUTES['[' + method + ']' + path] = Route(name, path, method, req_format, status, delay / 1000, forwarded, strategy, response_path)
        if status == 'MOCKED' and strategy in ['RANDOM', 'SEQUENCE']:
            files = {}
            for file in os.scandir(response_path):
                if file.is_file():
                    files[len(files)] = response_path + os.path.sep + file.name

            ROUTES['[' + method + ']' + path].files = files

        app.add_url_rule(path, name, callback, methods=[method])


if __name__ == '__main__':
    data = pd.read_excel(r'mocker.xlsx', sheet_name='Routes')

    df = pd.DataFrame(data, columns=['Name', 'Endpoint', 'Method', 'Format', 'Status', 'Delay [ms]', 'Forwarded endpoint',
                                     'Response strategy', 'Response path'])
    for r in range(len(df)):
        add_route(df['Name'][r], df['Endpoint'][r], df['Method'][r], df['Format'][r],
                  df['Status'][r], df['Delay [ms]'][r], df['Forwarded endpoint'][r],
                  df['Response strategy'][r], df['Response path'][r], )

    serve(app, host='0.0.0.0', port=5000)
