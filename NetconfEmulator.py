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
import logging
import os
import sys
import time
from netconf import error, server, util
from netconf import nsmap_add, NSMAP
from pymongo import MongoClient
from lxml import etree
import pyangbind.lib.serialise as serialise
import pyangbind.lib.pybindJSON as pybindJSON
from pyangbind.lib.serialise import pybindJSONDecoder
import json
from os import listdir, getcwd
from pydoc import locate
from internal import objects
from xmldiff import main as xmldiffmain

nsmap_add("sys", "urn:ietf:params:xml:ns:yang:ietf-system")


def process_changes(data_to_insert_xml, current_config_xml):

    config_tree = etree.ElementTree(current_config_xml)
    data_tree = etree.ElementTree(data_to_insert_xml)

    identifier_tag = ""
    identifier_value = ""

    for subitem_data in data_to_insert_xml.iter():
        if subitem_data.text.strip() != "":
            identifier_tag = subitem_data.tag
            identifier_value = subitem_data.text
            target_element_path = data_tree.getelementpath(subitem_data)
            target_element_data = data_tree.find(target_element_path).getparent()
            break

    logging.info("Identifier tag is " + identifier_tag)
    logging.info("Identifier value is " + identifier_value)
    logging.info("Target element data is " + etree.tostring(target_element_data, pretty_print=True))

    target_element_config = None

    for subitem_config in current_config_xml.iter():
        if subitem_config.tag == identifier_tag and subitem_config.text.strip() == identifier_value:
            logging.info("ENCONTRADO ITEM en config")
            element_path = config_tree.getelementpath(subitem_config)
            target_element_config = config_tree.find(element_path).getparent()
            break

    if target_element_config is not None:
        logging.info("Target element config is " + etree.tostring(target_element_config, pretty_print=True))


    if target_element_config is None:
        logging.info("NO EXISTE RECURSO, HAY QUE CREARLO")

    else:
        logging.info("SI EXISTE RECURSO, HAY QUE MODIFICARLO")
        logging.info(xmldiffmain.diff_trees(etree.ElementTree(target_element_config), etree.ElementTree(target_element_data)))

       # for conf_item in target_element_config.iter():
        #    for data_item in target_element_data.iter():
         #       if conf_item.tag == data_item.tag and conf_item.text.strip() != data_item.text.strip():
          #          conf_item.text = data_item.text

    return current_config_xml




def get_datastore(rpc):
    datastore_raw = etree.tostring(rpc[0][0][0])
    if "running" in datastore_raw:
        datastore = 'running'
    elif "candidate" in datastore_raw:
        datastore = 'candidate'
    elif "startup" in datastore_raw:
        datastore = 'startup'
    else:
        logging.info("Unknown datastore: "+datastore_raw)
        exit(1)

    return datastore


class NetconfEmulator(object):
    def __init__(self, port, host_key, auth, debug):
        self.server = objects.NetconfEmulatorServer(auth, self, port, host_key, debug)
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
                collection_data = collection.find_one({"_id": "running"})
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
                datastore_data = db[db_name].find_one({"_id": "running"})

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
        selected_datastore = get_datastore(rpc)
        # Empty filter
        if rpc[0].find('{*}filter') is None:
            # All configuration files should be appended
            db = dbclient.netconf
            data_elm = etree.Element('data', nsmap={None: 'urn:ietf:params:xml:ns:netconf:base:1.0'})
            i = 1
            for collection_name in db.list_collection_names():
                collection = getattr(db,collection_name)
                collection_data = collection.find_one({"_id": selected_datastore})
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
                datastore_data = db[db_name].find_one({"_id": selected_datastore})

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
        datastore_to_insert = get_datastore(rpc)
        data_to_insert_xml = etree.fromstring(etree.tostring(rpc[0][1]))

        for collection_name in db.list_collection_names():
            if self.used_model in collection_name:
                 collection = getattr(db, collection_name)
                 running_config = collection.find_one({"_id": datastore_to_insert})
                 del running_config["_id"]
                 running_config_b = pybindJSONDecoder.load_ietf_json(running_config, self.binding, collection_name)
                 running_config_xml_string = serialise.pybindIETFXMLEncoder.serialise(running_config_b)
                 running_config_xml = etree.fromstring(running_config_xml_string)

                 newconfig = process_changes(data_to_insert_xml, running_config_xml)

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

    host_key = os.getcwd() + "/hostkey/id_rsa"

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
