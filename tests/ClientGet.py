from netconf.client import NetconfSSHSession
from lxml import etree

session = NetconfSSHSession("localhost","8300","admin","admin")
config = session.get()

# TODO: Catch the RPCerror exception.
print(type(config))
print(etree.tostring(config,pretty_print=True))
session.close()
