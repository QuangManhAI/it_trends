from pymongo import MongoClient
import json

# uri của MongoDB Atlas
uri = 'mongodb+srv://manhnpq6852:200406@cluster0.jrtt3aq.mongodb.net/library?retryWrites=true&w=majority&appName=Cluster0'

try:
    client = MongoClient(uri, serverSelectionTimeoutMS=2000)
    client = MongoClient(uri)
    database = client['job_posting']
    collection = database['posting']

    print("Connect successful")
except Exception as e:
    print("Fail to connect to Atlas", e)

# with open('output.json', 'r', encoding='utf-8') as file:
#     raw_data = json.load(file)
# key =list(raw_data.keys())

# collection.insert_many(raw_data[key[0]])