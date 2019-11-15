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
#from xml import etree
from lxml import etree
import pyangbind.lib.serialise as serialise
import pyangbind.lib.pybindJSON as pybindJSON
from pyangbind.lib.serialise import pybindJSONDecoder
import json
from os import listdir, getcwd
from pydoc import locate
import itertools

nsmap_add("sys", "urn:ietf:params:xml:ns:yang:ietf-system")


def iterate_and_replace(data_to_insert_xml, current_config_xml):
    found = False
    iterator_config = current_config_xml.iter()
    for item_config in iterator_config:
        iterator_data = data_to_insert_xml.iter()
        for item_data in iterator_data:

            if (item_data.tag in item_config.tag or item_config.tag in item_data.tag) and item_data.text == item_config.text:
                item_data_text = str(item_data.text).strip()
                item_config_text = str(item_config.text).strip()
                if len(item_data_text) != 0 and len(item_config_text) != 0:
                    elem_to_change = item_config
                    new_conf = item_data
                    found = True

        if found:
            break


    config_tree = etree.ElementTree(current_config_xml)
    data_tree = etree.ElementTree(data_to_insert_xml)
    config_path_list = config_tree.getelementpath(elem_to_change).split("/{")
    config_path_list.pop()
    data_path_list = data_tree.getelementpath(new_conf).split("/{")
    data_path_list.pop()
    config_path = ''
    for it in config_path_list:
        config_path += '/{' + it
    config_path = config_path[2:len(config_path)]
    data_path = ''
    for it2 in data_path_list:
        data_path += '/{' + it2
    data_path = data_path[2:len(data_path)]

    config_element_to_change = config_tree.find(config_path)
    data_new_conf = data_tree.find(data_path)

    for conf_item in config_element_to_change.iter():
        for data_item in data_new_conf.iter():
            if (conf_item.tag in data_item.tag or data_item.tag in conf_item) and conf_item.text.strip() != data_item.text.strip():
                conf_item.text = data_item.text


    return current_config_xml




def get_datastore(datastore_raw):
    if "running" in datastore_raw:
        datastore = 'running'
    elif "candidate" in datastore_raw:
        datastore = 'candidate'
    elif "startup" in datastore_raw:
        datastore = 'startup'
    else:
        logging.info("Unknown datastore: "+datastore_raw)

    return datastore


class NetconfEmulator(object):
    def __init__(self, port, host_key, auth, debug):
        self.server = server.NetconfSSHServer(auth, self, port, host_key, debug)
        bindings_files_folder = getcwd() + "/bindings"
        bindings_folder_list = listdir(bindings_files_folder)
        for bind_file in bindings_folder_list:
            if "binding_" in bind_file and '.py' in bind_file:
                binding_file = bind_file
                break

        binding_file_fixed = binding_file.replace(".py", "")

        self.used_model = binding_file_fixed.split("_")[1]
        self.binding = locate('bindings.' + binding_file_fixed)

        logging.info("Used model: "+self.used_model)


    def close(self):
        self.server.close()

    def nc_append_capabilities(self, capabilities):  # pylint: disable=W0613
        """The server should append any capabilities it supports to capabilities"""
        util.subelm(capabilities,
                    "capability").text = "urn:ietf:params:netconf:capability:xpath:1.0"
        util.subelm(capabilities, "capability").text = NSMAP["sys"]

    def rpc_change_model(self, rpc):
        logging.info("Received change-model rpc: "+etree.tostring(rpc, pretty_print=True))

    def rpc_commit(self, rpc):
        logging.info("Received commit rpc: " + etree.tostring(rpc, pretty_print=True))


    def rpc_get(self, session, rpc, filter_or_none):  # pylint: disable=W0613
        logging.info("Received get rpc: "+etree.tostring(rpc, pretty_print=True))
        dbclient = MongoClient()
        if rpc[0].find('{*}filter') is None:
            # All configuration files should be appended
            data_elm = etree.Element('data', nsmap={None: 'urn:ietf:params:xml:ns:netconf:base:1.0'})
            i = 1
            db = dbclient.netconf
            logging.info(db.list_collections())
            for collection_name in db.list_collection_names():
                collection = getattr(db, collection_name)
                collection_data = collection.find_one()
                collection_data_1 = dict(collection_data)
                for element in collection_data:
                    if "id" in element:
                        del collection_data_1[element]
                collection_data = collection_data_1

                collection_binding = pybindJSONDecoder.load_ietf_json(collection_data, self.binding, collection_name)
                xml_data_string = serialise.pybindIETFXMLEncoder.serialise(collection_binding)
                xml_data = etree.XML(xml_data_string)
                data_elm.insert(i, xml_data)
                i += 1
            xml_response = data_elm

        else:
            # Parsing the database name form the rpc tag namespace
            db_base = rpc[0][1][0].tag.split('}')[0].split('/')[-1]
            db_source = rpc[0][1][0].tag.split('/')[2].split('.')[0]
            db_name = db_source + "-" + db_base
            # logging.info(db_name)

            # Finding the datastore requested
            db = dbclient.netconf
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

                database_data_binding = pybindJSONDecoder.load_ietf_json(datastore_data, self.binding, db_name)
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
            data_elm = etree.Element('data', nsmap={None: 'urn:ietf:params:xml:ns:netconf:base:1.0'})
            data_elm.insert(1, toreturn)
            logging.info(etree.tostring(data_elm, pretty_print=True))
            toreturn = data_elm

        return toreturn

    def rpc_get_config(self, session, rpc, source_elm, filter_or_none):  # pylint: disable=W0613
        logging.info("Received get-config rpc: " + etree.tostring(rpc, pretty_print=True))
        dbclient = MongoClient()
        # Empty filter
        if rpc[0].find('{*}filter') is None:
            # All configuration files should be appended
            db = dbclient.netconf
            data_elm = etree.Element('data', nsmap={None: 'urn:ietf:params:xml:ns:netconf:base:1.0'})
            i = 1
            for collection_name in db.list_collection_names():
                collection = getattr(db,collection_name)
                collection_data = collection.find_one()
                collection_data_1 = dict(collection_data)
                for element in collection_data:
                    if "id" in element:
                        del collection_data_1[element]
                collection_data = collection_data_1

                collection_binding = pybindJSONDecoder.load_ietf_json(collection_data, self.binding, collection_name)
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
            db = dbclient.netconf
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

                database_data_binding = pybindJSONDecoder.load_ietf_json(datastore_data, self.binding, db_name)
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
        logging.info("Received edit-config rpc: "+etree.tostring(rpc, pretty_print=True))
        dbclient = MongoClient()
        db = dbclient.netconf

        data_response = util.elm("ok")
        datastore_to_insert = get_datastore(etree.tostring(rpc[0][0][0]))
        data_to_insert_xml = etree.fromstring(etree.tostring(rpc[0][1]))


        for collection_name in db.list_collection_names():
            if self.used_model in collection_name:
                 collection = getattr(db, collection_name)
                 running_config = collection.find_one({"_id": datastore_to_insert})
                 del running_config["_id"]
                 running_config_b = pybindJSONDecoder.load_ietf_json(running_config, self.binding, collection_name)
                 running_config_xml_string = serialise.pybindIETFXMLEncoder.serialise(running_config_b)
                 running_config_xml = etree.fromstring(running_config_xml_string)
                 newconfig = iterate_and_replace(data_to_insert_xml, running_config_xml)
                 collection.delete_one({"_id": datastore_to_insert})
                 newconfig_string = etree.tostring(newconfig)
                 database_data = serialise.pybindIETFXMLDecoder.decode(newconfig_string, self.binding, collection_name)
                 database_string = pybindJSON.dumps(database_data, mode="ietf")
                 database_json = json.loads(database_string)
                 database_json["_id"] = datastore_to_insert
                 collection.insert_one(database_json)

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
    parser.add_argument("--password", default="admin", help='Netconf password')
    args = parser.parse_args(*margs)

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    host_key = "/home/cesar/.ssh/id_rsa"

    auth = server.SSHUserPassController(username=args.username, password=args.password)
    s = NetconfEmulator(args.port, host_key, auth, args.debug)

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
