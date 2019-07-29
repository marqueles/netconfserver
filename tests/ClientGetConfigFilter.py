from netconf.client import NetconfSSHSession

from lxml import etree

session = NetconfSSHSession("localhost" ,"8300" ,"admin" ,"admin")
config = session.get_config(select='<components xmlns="http://openconfig.net/yang/platform"><component/></components>')
#dom = xml.dom.minidom.parseString(config)
#print(dom.toprettyxml())


print(etree.tostring(config,pretty_print=True))
session.close()
