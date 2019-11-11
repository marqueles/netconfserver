from __future__ import print_function
from pymongo import MongoClient
import pyangbind.lib.serialise as serialise
import pyangbind.lib.pybindJSON as pybindJSON
import sys
import json
from os import listdir

if sys.argv[1] is None:
    print("The database reference is missing")
    exit(1)

if sys.argv[2] is None:
    print("The startup config is missing")
    exit(1)

binding = listdir("bindings")
print(binding)

database_model = sys.argv[1]
database_file = sys.argv[2]
database_name = database_model.split(".")[0]

print("Creating database", database_name)

dbclient = MongoClient()
db = dbclient.netconfserver

print(database_file)

print("Parsing data from the xml provided")
with open(database_file, 'r') as database_reader:
    data = database_reader.read().replace('\n', '')

database_data = serialise.pybindIETFXMLDecoder.decode(data, binding, database_name)
database_string = pybindJSON.dumps(database_data, mode="ietf")

#print(json_formatted_platform)

database_json= json.loads(database_string)
print("Inserting file into database")
collection = getattr(db, database_name)
result = collection.insert_one(database_json)
