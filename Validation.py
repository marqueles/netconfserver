from lxml import etree
import subprocess
import os


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
                 + operation + " | grep Issues -A100 1").read()

    file = open('res.txt', 'w+')
    file.write(o)
    file.close

    if not o == "":
        raise AttributeError
