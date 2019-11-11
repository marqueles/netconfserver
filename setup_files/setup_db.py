from __future__ import print_function
from pymongo import MongoClient
import pyangbind.lib.serialise as serialise
import pyangbind.lib.pybindJSON as pybindJSON
import sys
import json
from os import listdir, getcwd
from os.path import dirname
from pydoc import locate
import bindings

if sys.argv[1] is None:
    print("The database reference is missing")
    exit(1)

if sys.argv[2] is None:
    print("The startup config is missing")
    exit(1)

bindings_files_folder = getcwd()

database_model = sys.argv[1]
database_file = sys.argv[2]
database_name = database_model

bindings_folder_list = listdir(bindings_files_folder)
for bind_file in bindings_folder_list:
    if database_name in bind_file and '.py' in bind_file:
        binding_file = bind_file
        break

print(binding_file)
binding_file_fixed = binding_file.replace(".py","")
print(binding_file_fixed)

bind = locate('bindings.'+binding_file_fixed)

print(bind)

print("Creating database", database_name)

dbclient = MongoClient()
db = dbclient.netconfserver

print(database_file)

print("Parsing data from the xml provided")
with open(database_file, 'r') as database_reader:
    data = database_reader.read().replace('\n', '')

database_data = serialise.pybindIETFXMLDecoder.decode(data, binding, database_name)
database_string = pybindJSON.dumps(database_data, mode="ietf")

database_json= json.loads(database_string)
print("Inserting file into database")
collection = getattr(db, database_name)
result = collection.insert_one(database_json)
