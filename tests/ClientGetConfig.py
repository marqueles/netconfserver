from netconf.client import NetconfSSHSession
import xml.dom.minidom
from lxml import etree

session = NetconfSSHSession("localhost","8300","admin","admin")
config = session.get_config()

# TODO: Catch the RPCerror exception.

print(etree.tostring(config,pretty_print=True))
session.close()
