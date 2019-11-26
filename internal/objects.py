from netconf import server
import io
import logging
import sshutil.server as sshutilserver
import threading
from lxml import etree
import netconf.error as ncerror
from netconf import NSMAP
from netconf import qmap
from netconf import util

logger = logging.getLogger(__name__)

class NetconfEmulatorServer(sshutilserver.SSHServer):

    def __init__(self, server_ctl=None, server_methods=None, port=830, host_key=None, debug=False):
        self.server_methods = server_methods if server_methods is not None else server.NetconfMethods()
        self.session_id = 1
        self.session_locks_lock = threading.Lock()
        self.session_locks = {
            "running": 0,
            "candidate": 0,
        }
        super(NetconfEmulatorServer, self).__init__(
            server_ctl,
            server_session_class=NetconfEmulatorSession,
            port=port,
            host_key=host_key,
            debug=debug)

    def __del__(self):
        logger.error("Deleting %s", str(self))

    def _allocate_session_id(self):
        with self.lock:
            sid = self.session_id
            self.session_id += 1
            return sid

    def __str__(self):
        return "NetconfEmulatorServer(port={})".format(self.port)

    def unlock_target_any(self, session):
        """Unlock any targets locked by this session.

        Returns list of targets that this session had locked."""
        locked = []
        with self.lock:
            with self.session_locks_lock:
                sid = session.session_id
                for target in self.session_locks:
                    if self.session_locks[target] == sid:
                        self.session_locks[target] = 0
                        locked.append(target)
                return locked

    def unlock_target(self, session, target):
        """Unlock the given target."""
        with self.lock:
            with self.session_locks_lock:
                if self.session_locks[target] == session.session_id:
                    self.session_locks[target] = 0
                    return True
                return False

    def lock_target(self, session, target):
        """Try to obtain target lock.
        Return 0 on success or the session ID of the lock holder.
        """
        with self.lock:
            with self.session_locks_lock:
                if self.session_locks[target]:
                    return self.session_locks[target]
                self.session_locks[target] = session.session_id
                return 0

    def is_target_locked(self, target):
        """Returns the sesions ID who owns the lock or 0 if not locked."""
        with self.lock:
            with self.session_locks_lock:
                if target not in self.session_locks:
                    return None
                return self.session_locks[target]


class NetconfEmulatorSession(server.NetconfServerSession):

    def __init__(self, channel, server, unused_extra_args, debug):
        super(NetconfEmulatorSession, self).__init__(channel, server, unused_extra_args, debug)


    def _reader_handle_message(self, msg):
        if not self.session_open:
            return

        try:
            tree = etree.parse(io.BytesIO(msg.encode('utf-8')))
            if not tree:
                raise ncerror.SessionError(msg, "Invalid XML from client.")
        except etree.XMLSyntaxError:
            logger.warning("Closing session due to malformed message")
            raise ncerror.SessionError(msg, "Invalid XML from client.")

        rpcs = tree.xpath("/nc:rpc", namespaces=NSMAP)
        if not rpcs:
            raise ncerror.SessionError(msg, "No rpc found")

        for rpc in rpcs:
            try:
                msg_id = rpc.get('message-id')
                if self.debug:
                    logger.debug("%s: Received rpc message-id: %s", str(self), msg_id)
            except (TypeError, ValueError):
                raise ncerror.SessionError(msg, "No valid message-id attribute found")

            try:
                # Get the first child of rpc as the method name
                rpc_method = rpc.getchildren()
                if len(rpc_method) != 1:
                    if self.debug:
                        logger.debug("%s: Bad Msg: msg-id: %s", str(self), msg_id)
                    raise ncerror.MalformedMessageRPCError(rpc)
                rpc_method = rpc_method[0]

                rpcname = rpc_method.tag.replace(qmap('nc'), "")
                params = rpc_method.getchildren()
                paramslen = len(params)
                lock_target = None

                if self.debug:
                    logger.debug("%s: RPC: %s: paramslen: %s", str(self), rpcname, str(paramslen))

                if rpcname == "close-session":
                    # XXX should be RPC-unlocking if need be
                    if self.debug:
                        logger.debug("%s: Received close-session msg-id: %s", str(self), msg_id)
                    self._send_rpc_reply(etree.Element("ok"), rpc)
                    self.close()
                    # XXX should we also call the user method if it exists?
                    return
                elif rpcname == "kill-session":
                    # XXX we are supposed to cleanly abort anything underway
                    if self.debug:
                        logger.debug("%s: Received kill-session msg-id: %s", str(self), msg_id)
                    self._send_rpc_reply(etree.Element("ok"), rpc)
                    self.close()
                    # XXX should we also call the user method if it exists?
                    return
                elif rpcname == "get":
                    # Validate GET parameters

                    if paramslen > 1:
                        # XXX need to specify all elements not known
                        raise ncerror.MalformedMessageRPCError(rpc)
                    if params and not util.filter_tag_match(params[0], "nc:filter"):
                        raise ncerror.UnknownElementProtoError(rpc, params[0])
                    if not params:
                        params = [None]
                elif rpcname == "get-config":
                    # Validate GET-CONFIG parameters

                    if paramslen > 2:
                        # XXX Should be ncerror.UnknownElementProtoError? for each?
                        raise ncerror.MalformedMessageRPCError(rpc)
                    source_param = rpc_method.find("nc:source", namespaces=NSMAP)
                    if source_param is None:
                        raise ncerror.MissingElementProtoError(rpc, util.qname("nc:source"))
                    filter_param = None
                    if paramslen == 2:
                        filter_param = rpc_method.find("nc:filter", namespaces=NSMAP)
                        if filter_param is None:
                            unknown_elm = params[0] if params[0] != source_param else params[1]
                            raise ncerror.UnknownElementProtoError(rpc, unknown_elm)
                    params = [source_param, filter_param]
                elif rpcname == "lock" or rpcname == "unlock":
                    if paramslen != 1:
                        raise ncerror.MalformedMessageRPCError(rpc)
                    target_param = rpc_method.find("nc:target", namespaces=NSMAP)
                    if target_param is None:
                        raise ncerror.MissingElementProtoError(rpc, util.qname("nc:target"))
                    elms = target_param.getchildren()
                    if len(elms) != 1:
                        raise ncerror.MissingElementProtoError(rpc, util.qname("nc:target"))
                    lock_target = elms[0].tag.replace(qmap('nc'), "")
                    if lock_target not in ["running", "candidate"]:
                        raise ncerror.BadElementProtoError(rpc, util.qname("nc:target"))
                    params = [lock_target]

                    if rpcname == "lock":
                        logger.error("%s: Lock Target: %s", str(self), lock_target)
                        # Try and obtain the lock.
                        locksid = self.server.lock_target(self, lock_target)
                        if locksid:
                            raise ncerror.LockDeniedProtoError(rpc, locksid)
                    elif rpcname == "unlock":
                        logger.error("%s: Unlock Target: %s", str(self), lock_target)
                        # Make sure we have the lock.
                        locksid = self.server.is_target_locked(lock_target)
                        if locksid != self.session_id:
                            # An odd error to return
                            raise ncerror.LockDeniedProtoError(rpc, locksid)

                #------------------
                # Call the method.
                #------------------

                try:
                    # Handle any namespaces or prefixes in the tag, other than
                    # "nc" which was removed above. Of course, this does not handle
                    # namespace collisions, but that seems reasonable for now.
                    rpcname = rpcname.rpartition("}")[-1]
                    method_name = "rpc_" + rpcname.replace('-', '_')
                    method = getattr(self.methods, method_name, None)

                    if method is None:
                        if rpcname in self.handled_rpc_methods:
                            self._send_rpc_reply(etree.Element("ok"), rpc)
                            method = None
                        else:
                            method = self._rpc_not_implemented

                    if method is not None:
                        if self.debug:
                            logger.debug("%s: Calling method: %s", str(self), method_name)
                        reply = method(self, rpc, *params)
                        self._send_rpc_reply(reply, rpc)
                except Exception:
                    # If user raised error unlock if this was lock
                    if rpcname == "lock" and lock_target:
                        self.server.unlock_target(self, lock_target)
                    raise

                # If this was unlock and we're OK, release the lock.
                if rpcname == "unlock":
                    self.server.unlock_target(self, lock_target)

            except ncerror.MalformedMessageRPCError as msgerr:
                if self.new_framing:
                    if self.debug:
                        logger.debug("%s: MalformedMessageRPCError: %s", str(self), str(msgerr))
                    self.send_message(msgerr.get_reply_msg())
                else:
                    # If we are 1.0 we have to simply close the connection
                    # as we are not allowed to send this error
                    logger.warning("Closing 1.0 session due to malformed message")
                    raise ncerror.SessionError(msg, "Malformed message")
            except ncerror.RPCServerError as error:
                if self.debug:
                    logger.debug("%s: RPCServerError: %s", str(self), str(error))
                self._send_rpc_reply_error(error)
            except EOFError:
                if self.debug:
                    logger.debug("%s: Got EOF in reader_handle_message", str(self))
                error = ncerror.RPCSvrException(rpc, EOFError("EOF"))
                self._send_rpc_reply_error(error)
            except Exception as exception:
                if self.debug:
                    logger.debug("%s: Got unexpected exception in reader_handle_message: %s",
                                 str(self), str(exception))
                error = ncerror.RPCSvrException(rpc, exception)
                self._send_rpc_reply_error(error)