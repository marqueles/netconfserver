from __future__ import print_function
from pymongo import MongoClient
import pyangbind.lib.serialise as serialise
import pyangbind.lib.pybindJSON as pybindJSON
import sys
import json
from os import listdir, getcwd
from pydoc import locate

if sys.argv[1] is None:
    print("The database reference is missing")
    exit(1)

if sys.argv[2] is None:
    print("The startup config is missing")
    exit(1)

bindings_files_folder = getcwd()+"/bindings"

database_model = sys.argv[1]
database_file = sys.argv[2]
database_name = database_model

bindings_folder_list = listdir(bindings_files_folder)
for bind_file in bindings_folder_list:
    if database_name in bind_file and '.py' in bind_file:
        binding_file = bind_file
        break

binding_file_fixed = binding_file.replace(".py","")

binding = locate('bindings.'+binding_file_fixed)

print("Creating database", database_name)

dbclient = MongoClient()
db = dbclient.netconf

print(database_file)

print("Parsing data from the xml provided")
with open(database_file, 'r') as database_reader:
    data = database_reader.read().replace('\n', '')

database_data = serialise.pybindIETFXMLDecoder.decode(data, binding, database_name)
database_string = pybindJSON.dumps(database_data, mode="ietf")

startup_json = json.loads(database_string)
startup_json["_id"] = "startup"
candidate_json = json.loads(database_string)
candidate_json["_id"] = "candidate"
running_json = json.loads(database_string)
running_json["_id"] = "running"

print("Inserting files into database")
collection = getattr(db, database_name)
#result_startup = collection.insert_one(startup_json)
#result_candidate = collection.insert_one(candidate_json)
result_running = collection.insert_one(running_json)
