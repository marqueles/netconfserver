from netconf.client import NetconfSSHSession

from lxml import etree

session = NetconfSSHSession("localhost", "8300", "admin", "admin")
config = session.get_config(select='<components xmlns="http://openconfig.net/yang/platform"><component><config>'
                                   '</config></component></components>')


print(etree.tostring(config,pretty_print=True))
session.close()
