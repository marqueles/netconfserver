from lxml import etree
import pymongo
import os
import datetime


def register(operation, status, info):
    myclient = pymongo.MongoClient("mongodb://localhost:27017/")
    mydb = myclient["mydatabase"]
    collection = mydb["log_validation"]

    rpc = {
        "datetime" : datetime.datetime.utcnow(),
        "operation" : operation,
        "status" : status
    }

    if info:
        rpc["info"] = info

    collection.insert_one(rpc)


def validate_rpc(rpc, operation):

    # Writing data to file
    data_to_insert_string = etree.tostring(rpc, pretty_print=True)
    file = open('validation.xml', 'w+')
    file.write(data_to_insert_string)
    file.close()

    modules = os.popen('cat validation.xml | grep http | cut -d\'"\' -f2 | grep http | cut -d\'"\' -f2').read()
    dependencies = os.popen("python dependencies.py "+modules).read()

    o = os.popen("pyang -f xmlverifier "+''.join(dependencies.splitlines()) +
                 " -o example.tree -p all/ --xmlverifier-xml validation.xml --xmlverifier-operation "
                 + operation + "| grep Issues -A100").read()

    file = open('res.txt', 'w+')
    file.write(o)
    file.close

    if not o == "":
        register(operation, "error", o)
        raise Exception("the model in the system is not syntactically valid")
    else:
        register(operation, "success")
