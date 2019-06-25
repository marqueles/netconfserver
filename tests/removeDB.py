import pymongo

myclient = pymongo.MongoClient("mongodb://localhost:27017/")
db = myclient["mydatabase"]

collection = db["test-collection"]

collection.remove({})