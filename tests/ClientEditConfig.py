from netconf.client import NetconfSSHSession
import xmltodict
from xmljson import badgerfish as bf
from lxml import etree
with open('tests/testdata2.xml', 'r') as file:
    data = file.read().replace('\n', '')

jsondata = xmltodict.parse(data)
etreeX = bf.etree(jsondata)

print(type(etreeX[0]))
newconf = etreeX[0]
session = NetconfSSHSession("localhost","8300","admin","admin")
edit_config_response = session.edit_config(newconf=data)

print(etree.tostring(edit_config_response,pretty_print=True))
session.close()
