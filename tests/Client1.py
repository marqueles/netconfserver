from netconf.client import NetconfSSHSession
import xml.dom.minidom
from lxml import etree

session = NetconfSSHSession("localhost","8300","admin","admin")
config = session.get_config()
#dom = xml.dom.minidom.parseString(config)
#print(dom.toprettyxml())

print(etree.tostring(config,pretty_print=True))
session.close()
