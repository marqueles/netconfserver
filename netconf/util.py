# -*- coding: utf-8 eval: (yapf-mode 1) -*-
#
# March 31 2015, Christian Hopps <chopps@gmail.com>
#
# Copyright (c) 2015, Deutsche Telekom AG
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
from __future__ import absolute_import, division, unicode_literals, print_function, nested_scopes
import copy
import logging
from lxml import etree
from netconf import NSMAP
from netconf import error
from netconf import qmap
# Tries to somewhat implement RFC6241 filtering
logger = logging.getLogger(__name__)


def qname(tag):
    try:
        return etree.QName(tag)
    except ValueError:
        prefix, base = tag.split(":")
        return etree.QName(NSMAP[prefix], base)


def elm(tag, attrib=None, **extra):
    if attrib is None:
        attrib = dict()
    return etree.Element(qname(tag), attrib, **extra)


def leaf_elm(tag, value, attrib=None, **extra):
    e = elm(tag, attrib, **extra)
    e.text = str(value)
    return e


# Create another name for leaf_elm function
leaf = leaf_elm


def subelm(pelm, tag, attrib=None, **extra):
    if attrib is None:
        attrib = dict()
    return etree.SubElement(pelm, qname(tag), attrib, **extra)


def is_selection_node(felm):
    ftext = felm.text
    return ftext is None or not ftext.strip()


def xpath_filter_result(data, xpath):
    """Filter a result given an xpath expression.

    :param data: The nc:data result element.
    :param xpath: The xpath expression string.
    :returns: New nc:data result element pruned by the xpath expression.

    >>> xml = '''
    ... <data>
    ...   <devs>
    ...     <dev>
    ...       <name>dev1</name>
    ...       <slots>1</slots>
    ...     </dev>
    ...     <dev>
    ...       <name>dev2</name>
    ...       <slots>2</slots>
    ...     </dev>
    ...     <dev>
    ...       <name>dev3</name>
    ...       <slots>3</slots>
    ...     </dev>
    ...   </devs>
    ... </data>
    ... '''
    >>> data = etree.fromstring(xml.replace(' ', '').replace('\\n', ''))
    >>> result = xpath_filter_result(data, "/devs/dev")
    >>> etree.tounicode(result)
    '<data><devs><dev><name>dev1</name><slots>1</slots></dev><dev><name>dev2</name><slots>2</slots></dev><dev><name>dev3</name><slots>3</slots></dev></devs></data>'
    >>> result = xpath_filter_result(data, "/devs/dev[name='dev1']")
    >>> etree.tounicode(result)
    '<data><devs><dev><name>dev1</name><slots>1</slots></dev></devs></data>'
    >>> result = xpath_filter_result(data, "/devs/dev[name='dev2']")
    >>> etree.tounicode(result)
    '<data><devs><dev><name>dev2</name><slots>2</slots></dev></devs></data>'
    >>> result = xpath_filter_result(data, "/devs/dev[name='dev2'] | /devs/dev[name='dev1']")
    >>> etree.tounicode(result)
    '<data><devs><dev><name>dev1</name><slots>1</slots></dev><dev><name>dev2</name><slots>2</slots></dev></devs></data>'
    >>> result = xpath_filter_result(data, "/devs/dev[name='dev1'] | /devs/dev[name='dev2']")
    >>> etree.tounicode(result)
    '<data><devs><dev><name>dev1</name><slots>1</slots></dev><dev><name>dev2</name><slots>2</slots></dev></devs></data>'
    >>> result = xpath_filter_result(data, "/devs/dev[name='dev1'] | /devs/dev[slots='2']")
    >>> etree.tounicode(result)
    '<data><devs><dev><name>dev1</name><slots>1</slots></dev><dev><name>dev2</name><slots>2</slots></dev></devs></data>'
    """

    # First get a copy we can safely modify.
    data = copy.deepcopy(data)

    results = []
    children = []

    # XXX Need to reset the namespace declarations to those found in the context of the filter node.

    # Have to re-root the children to avoid having to match "/nc:data"
    for child in data.getchildren():
        data.remove(child)
        children.append(child)
        newtree = etree.ElementTree(child)
        results.extend(newtree.xpath(xpath, namespaces=NSMAP))

    # Add the children of data back.
    for child in children:
        data.append(child)

    # Mark the tree up
    for result in results:
        # Mark all children
        for e in result.iterdescendants():
            e.attrib['__filter_marked__'] = ""
        # Mark this element and all parents
        while result is not data:
            result.attrib['__filter_marked__'] = ""
            result = result.getparent()

    def prunedecendants(e):
        for child in e.getchildren():
            if '__filter_marked__' not in child.attrib:
                e.remove(child)
            else:
                prunedecendants(child)
                del child.attrib['__filter_marked__']

    prunedecendants(data)

    return data


def subtree_filter(data,rpc):

    # Aqui estan los distintos componentes de la base de datos
    for filter_item in rpc.iter(qmap('nc')+'filter'):
        filter_tree = filter_item

    unprunned_toreturn = data
    filter_elm = filter_tree

    logging.info(etree.tostring(unprunned_toreturn,pretty_print=True))
    logging.info(etree.tostring(filter_elm,pretty_print=True))

    def check_content_match(data):
        response = False
        for child in data:
            if not(child.text == '' or child.text is None):
                response = True
        return response

    def prune_descendants(data,filter):
        logging.info("The child " + filter.tag + " is a content match: " + str(check_content_match(filter)))
        if check_content_match(filter):

            # logging.info("Elements of the content match: ------------------")
            # logging.info(etree.tostring(data,pretty_print=True))
            # logging.info(etree.tostring(filter, pretty_print=True))

            #find content match element
            for child in filter:
                if not(child.text is '' or child.text is None):
                    matching_elem = child
            # logging.info("Looking for the element " + matching_elem.tag + " , " + matching_elem.text)

            # Checking if the current elem matches the seached one
            if data.find(matching_elem.tag) is not None and data.find(matching_elem.tag).text == matching_elem.text:
                # logging.info("This element matches")
                #logging.info(etree.tostring(data,pretty_print=True))
                #logging.info(etree.tostring(filter, pretty_print=True))
                if len(list(filter)) > 1:
                    matching_elem.text = ''
                    logging.info("Containment nodes inside")
                    logging.info(etree.tostring(data,pretty_print=True))
                    logging.info(etree.tostring(filter, pretty_print=True))
                    prune_descendants(data,filter)
            else:
                # logging.info("This element doesnt match")
                data.getparent().remove(data)

        else:
            for child in data:

                if len(list(filter)) is not 0:
                    if filter.find(child.tag) is not None:
                        logging.info("Element " + child.tag + " found in data, so persisting it")
                        prune_descendants(child, filter[0])

                    else:
                        logging.info("Element " + child.tag + " missing in data, deleting it")
                        data.remove(child)

    prune_descendants(unprunned_toreturn,filter_elm)

    #logging.info(etree.tostring(unprunned_toreturn,pretty_print=True))

    return unprunned_toreturn


def filter_results(rpc, data, filter_or_none, debug=False):
    """Check for a user filter and prune the result data accordingly.

    :param rpc: An RPC message element.
    :param data: The data to filter.
    :param filter_or_none: Filter element or None.
    :type filter_or_none: `lxml.Element`
    """
    if filter_or_none is None:
        return data

    if 'type' not in filter_or_none.attrib:
        # Check for the pathalogical case of empty filter since that's easy to implement.
        if not filter_or_none.getchildren():
            return elm("data")
        # xpf = Convert subtree filter to xpath!

    elif filter_or_none.attrib['type'] == "subtree":
        logger.debug("Filtering with subtree")
        return subtree_filter(data,rpc)

    elif filter_or_none.attrib['type'] == "xpath":
        if 'select' not in filter_or_none.attrib:
            raise error.MissingAttributeProtoError(rpc, filter_or_none, "select")
        xpf = filter_or_none.attrib['select']

        logger.debug("Filtering on xpath expression: %s", str(xpf))
        return xpath_filter_result(data, xpf)
    else:
        msg = "unexpected type: " + str(filter_or_none.attrib['type'])
        raise error.BadAttributeProtoError(rpc, filter_or_none, "type", message=msg)




__author__ = 'Christian Hopps'
__date__ = 'March 31 2015'
__version__ = '1.0'
__docformat__ = "restructuredtext en"
