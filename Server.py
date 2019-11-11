# -*- coding: utf-8 eval: (yapf-mode 1) -*-
# February 24 2018, Christian Hopps <chopps@gmail.com>
#
# Copyright (c) 2018, Deutsche Telekom AG.
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
from __future__ import absolute_import, division, unicode_literals, print_function, nested_scopes
import argparse
import datetime
import logging
import os
import platform
import socket
import sys
import time
from netconf import error, server, util
from netconf import nsmap_add, NSMAP
from pymongo import MongoClient
from lxml import etree
import xml.etree.ElementTree as ET
from lxml import objectify
import Validation
import pyangbind.lib.serialise as serialise
import pyangbind.lib.pybindJSON as pybindJSON
from pyangbind.lib.serialise import pybindJSONDecoder
import bindings
import json

nsmap_add("sys", "urn:ietf:params:xml:ns:yang:ietf-system")


def parse_password_arg(password):
    if password:
        if password.startswith("env:"):
            unused, key = password.split(":", 1)
            password = os.environ[key]
        elif password.startswith("file:"):
            unused, path = password.split(":", 1)
            password = open(path).read().rstrip("\n")
    return password


def date_time_string(dt):
    tz = dt.strftime("%z")
    s = dt.strftime("%Y-%m-%dT%H:%M:%S.%f")
    if tz:
        s += " {}:{}".format(tz[:-2], tz[-2:])
    return s


class SystemServer(object):
    def __init__(self, port, host_key, auth, debug):
        self.server = server.NetconfSSHServer(auth, self, port, host_key, debug)

    def close(self):
        self.server.close()

    def nc_append_capabilities(self, capabilities):  # pylint: disable=W0613
        """The server should append any capabilities it supports to capabilities"""
        util.subelm(capabilities,
                    "capability").text = "urn:ietf:params:netconf:capability:xpath:1.0"
        util.subelm(capabilities, "capability").text = NSMAP["sys"]

    def rpc_get(self, session, rpc, filter_or_none):  # pylint: disable=W0613
        if rpc[0].find('{*}filter') is None:
            # All configuration files should be appended
            dbclient = MongoClient()
            db = dbclient.netconfserver
            data_elm = etree.Element('data', nsmap={None: 'urn:ietf:params:xml:ns:netconf:base:1.0'})
            i = 1
            logging.info(db.list_collections())
            for collection_name in db.list_collection_names():
                collection = getattr(db, collection_name)
                collection_data = collection.find_one()
                collection_data_1 = dict(collection_data)
                for element in collection_data:
                    if "id" in element:
                        del collection_data_1[element]
                collection_data = collection_data_1

                collection_binding = pybindJSONDecoder.load_ietf_json(collection_data, binding, collection_name)
                xml_data_string = serialise.pybindIETFXMLEncoder.serialise(collection_binding)
                xml_data = etree.XML(xml_data_string)
                data_elm.insert(i, xml_data)
                i += 1
            xml_response = data_elm

        # Only supportedd datastore so far is platform
        else:
            # Parsing the database name form the rpc tag namespace
            db_base = rpc[0][1][0].tag.split('}')[0].split('/')[-1]
            db_source = rpc[0][1][0].tag.split('/')[2].split('.')[0]
            db_name = db_source + "-" + db_base
            # logging.info(db_name)

            # Finding the datastore requested
            dbclient = MongoClient()
            db = dbclient.netconfserver
            names = db.list_collection_names()
            # logging.info(names)

            if db_name in names:

                logging.info("Found the datastore requested")

                # Retrieving the data from the datastore
                datastore_name = db_name + ":" + rpc[0][1][0].tag.split('}')[1]
                datastore_data = db[db_name].find_one()

                datastore_data_1 = dict(datastore_data)
                for element in datastore_data:
                    if "id" in element:
                        del datastore_data_1[element]
                datastore_data = datastore_data_1

                database_data_binding = pybindJSONDecoder.load_ietf_json(datastore_data, binding, db_name)
                logging.info(database_data_binding)

                # Parsing the data to xml
                xml_data = serialise.pybindIETFXMLEncoder.serialise(database_data_binding)
                xml_response = etree.XML(xml_data)

            else:
                raise AttributeError("The requested datastore is not supported")

        # Validation.validate_rpc(response, "get-config")
        toreturn = util.filter_results(rpc, xml_response, filter_or_none, self.server.debug)

        if "data" not in toreturn.tag:
            logging.info("data not header")
            nsmap = {None: 'urn:ietf:params:xml:ns:netconf:base:1.0'}
            data_elm = etree.Element('data', nsmap={None: 'urn:ietf:params:xml:ns:netconf:base:1.0'})
            data_elm.insert(1, toreturn)
            logging.info(etree.tostring(data_elm, pretty_print=True))
            toreturn = data_elm

        return toreturn

    def rpc_get_config(self, session, rpc, source_elm, filter_or_none):  # pylint: disable=W0613

        # logging.info(etree.tostring(rpc, pretty_print=True))
        # Empty filter
        if rpc[0].find('{*}filter') is None:
            # All configuration files should be appended
            dbclient = MongoClient()
            db = dbclient.netconfserver
            data_elm = etree.Element('data', nsmap={None: 'urn:ietf:params:xml:ns:netconf:base:1.0'})
            i = 1
            logging.info(db.list_collections())
            for collection_name in db.list_collection_names():
                collection = getattr(db,collection_name)
                collection_data = collection.find_one()
                collection_data_1 = dict(collection_data)
                for element in collection_data:
                    if "id" in element:
                        del collection_data_1[element]
                collection_data = collection_data_1

                collection_binding = pybindJSONDecoder.load_ietf_json(collection_data, binding, collection_name)
                xml_data_string = serialise.pybindIETFXMLEncoder.serialise(collection_binding)
                xml_data = etree.XML(xml_data_string)
                data_elm.insert(i,xml_data)
                i += 1
            xml_response = data_elm

        # Only supportedd datastore so far is platform
        else:
            # Parsing the database name form the rpc tag namespace
            db_base = rpc[0][1][0].tag.split('}')[0].split('/')[-1]
            db_source = rpc[0][1][0].tag.split('/')[2].split('.')[0]
            db_name = db_source + "-" + db_base
            #logging.info(db_name)

            # Finding the datastore requested
            dbclient = MongoClient()
            db = dbclient.netconfserver
            names = db.list_collection_names()
            #logging.info(names)

            if db_name in names:

                logging.info("Found the datastore requested")

                # Retrieving the data from the datastore
                datastore_name = db_name + ":" + rpc[0][1][0].tag.split('}')[1]
                datastore_data = db[db_name].find_one()

                datastore_data_1 = dict(datastore_data)
                for element in datastore_data:
                    if "id" in element:
                        del datastore_data_1[element]
                datastore_data = datastore_data_1

                database_data_binding = pybindJSONDecoder.load_ietf_json(datastore_data, binding, db_name)
                logging.info(database_data_binding)

                # Parsing the data to xml
                xml_data = serialise.pybindIETFXMLEncoder.serialise(database_data_binding)
                xml_response = etree.XML(xml_data)

            else:
                raise AttributeError("The requested datastore is not supported")

        # Validation.validate_rpc(response, "get-config")
        toreturn = util.filter_results(rpc, xml_response, filter_or_none, self.server.debug)
        util.trimstate(toreturn)

        if "data" not in toreturn.tag:
            logging.info("data not header")
            nsmap = {None : 'urn:ietf:params:xml:ns:netconf:base:1.0'}
            data_elm = etree.Element('data',nsmap={None : 'urn:ietf:params:xml:ns:netconf:base:1.0'})
            data_elm.insert(1,toreturn)
            logging.info(etree.tostring(data_elm,pretty_print=True))
            toreturn = data_elm

        return toreturn

    def rpc_edit_config(self, unused_session, rpc, *unused_params):
        """XXX API subject to change -- unfinished"""

        print(rpc)

        data_response = util.elm("ok")
        data_to_insert = rpc[0][1]

        # Validation.validate_rpc(data_to_insert,"edit-config")

        # data_to_insert = data_to_insert.find("{http://openconfig.net/yang/platform}data")
        # data_to_insert_string = etree.tostring(data_to_insert, pretty_print=True, encoding='unicode')
        # parser = etree.XMLParser(remove_blank_text=True)
        # data_to_insert = etree.fromstring(data_to_insert_string, parser=parser)
        # data_to_insert_string = etree.tostring(data_to_insert, pretty_print=True)

        # logging.info(data_to_insert_string)

        # open("configuration/platform.xml", "w").write(data_to_insert_string)

        return data_response

    def rpc_system_restart(self, session, rpc, *params):
        raise error.AccessDeniedAppError(rpc)

    def rpc_system_shutdown(self, session, rpc, *params):
        raise error.AccessDeniedAppError(rpc)


def main(*margs):
    parser = argparse.ArgumentParser("Netconf Agent Emulator")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument('--port', type=int, default=8300, help='Netconf server port')
    parser.add_argument("--username", default="admin", help='Netconf username')
    parser.add_argument("--password", default="admin", help='Use "env:" or "file:" prefix to specify source')
    args = parser.parse_args(*margs)

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    args.password = parse_password_arg(args.password)
    host_key = "/home/cesar/.ssh/id_rsa"

    auth = server.SSHUserPassController(username=args.username, password=args.password)
    s = SystemServer(args.port, host_key, auth, args.debug)

    if sys.stdout.isatty():
        print("^C to stop emulator")
    try:
        while True:
            time.sleep(1)
    except Exception:
        print("Quitting emulator")

    s.close()


if __name__ == "__main__":
    main()
