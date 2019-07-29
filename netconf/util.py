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

    # Searches for matching namepsace filter node in data
    def matching_ns(data, filter_item):

        #logger.info(filter_item.tag)
        for data_item in data.iter():
            if 'xmlns' in data_item.attrib:
                if ('{' + data_item.attrib['xmlns'] + '}' + data_item.tag) == filter_item.tag:
                    return data_item
        return elm("data")

    toreturn = elm("data")

    def clean_tree(element, filter_elem):
        for child in filter_elem:

            if child.contains('{'):
                logger.info("component:" + child.tag  + "so checking for matching ns")

            if element.find(child.tag) is None:
                #elements are not mathcing because of ns
                logger.info("cleaning component:" + child.tag)
                #element.remove(child)
            else:
                logger.info("maintaining component:" + child.tag)
                clean_tree(child, element.find(child.tag))
    # This should find the items to filer, then find the  parent and include it to the parent in toreturn
    for filter_item in filter_tree:
        matching_elem = matching_ns(data, filter_item)
        """
        for child in filter_item:
            logger.info(child.base)

        logger.info(etree.tostring(matching_elem, pretty_print=True))
        logger.info(matching_elem.tag)
        for child in matching_elem:
            logger.info(child.tag)
        #logger.info(etree.tostring(filter_item, pretty_print=True))
        logger.info(filter_item.tag)
        for child in filter_item:
            logger.info(child.tag)
        """

        clean_tree(matching_elem, filter_item)
        ## hace falta iterar y filtrar este toreturn incluido
        logger.info((filter_item))

        toreturn.append(matching_elem)
    return toreturn


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
