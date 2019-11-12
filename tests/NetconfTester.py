from ncclient import manager
from argparse import ArgumentParser
from lxml import etree as et

def main(*margs):
    parser = ArgumentParser("Netconf Client Tester")
    parser.add_argument('--host',default='localhost', help='Netconf host')
    parser.add_argument('--port', type=int, default=8300, help='Netconf server port')
    parser.add_argument("--username", default="admin", help='Netconf username')
    parser.add_argument("--password", default="admin", help='Netconf password')
    parser.add_argument("--rpc", default='get-config', help="RPC to execute (get-config, get, edit-config)")
    parser.add_argument("--datastore", default='running', help="Netconf datastore (running or candidate). Only for get-config and edit-config RPCs.")
    parser.add_argument("--filter_or_config", default=None,
                        help="RPC filter field for get-config and get RPCs or RPC config field for edit-config RPC.")
    args = parser.parse_args(*margs)

    host = args.host
    port = args.port
    username = args.username
    password = args.password
    rpc = args.rpc
    datastore = args.datastore
    filter_or_config = args.filter_or_config

    man = manager.connect(host=host, port=port, username=username, password=password, timeout=120, hostkey_verify=False, look_for_keys=False, allow_agent=False)

    if rpc == 'get-config':

        get_config_response = man.get_config(datastore, filter_or_config)
        print get_config_response

    elif rpc == 'get':

        get_response = man.get(filter_or_config)
        print get_response

    elif rpc == 'edit-config':

        edit_config_response = man.edit_config(datastore, 'merge', filter_or_config, 120)
        print edit_config_response

    else:
        print("Unknown RPC")


if __name__ == "__main__":
    main()
