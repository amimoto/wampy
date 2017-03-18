import logging
import socket
import ssl
import uuid
from base64 import encodestring
from socket import error as socket_error

import greenlet

from wampy.constants import WEBSOCKET_SUBPROTOCOLS, WEBSOCKET_VERSION
from wampy.errors import (
    IncompleteFrameError, ConnectionError, WampProtocolError)

from . frames import ClientFrame, ServerFrame


logger = logging.getLogger(__name__)


class WebSocket(object):

    def __init__(self, host, port, websocket_location="ws"):
        self.host = host
        self.port = port
        self.websocket_location = websocket_location.lstrip('/')
        self.key = encodestring(uuid.uuid4().bytes).decode('utf-8').strip()
        self.socket = None

    def _connect(self):
        _socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            _socket.connect((self.host, self.port))
        except socket_error as exc:
            if exc.errno == 61:
                logger.error(
                    'unable to connect to %s:%s', self.host, self.port
                )

            raise

        self.socket = _socket

    def _upgrade(self):
        handshake_headers = self._get_handshake_headers()
        handshake = '\r\n'.join(handshake_headers) + "\r\n\r\n"

        logger.debug("WAMP Connection handshake: %s", ', '.join(
            handshake_headers))

        self.socket.send(handshake)
        self.status, self.headers = self._read_handshake_response()

        logger.debug("WAMP Connection reply: %s", self.headers)

    def _get_handshake_headers(self):
        """ Do an HTTP upgrade handshake with the server.

        Websockets upgrade from HTTP rather than TCP largely because it was
        assumed that servers which provide websockets will always be talking to
        a browser. Maybe a reasonable assumption once upon a time...

        The headers here will go a little further and also agree the
        WAMP websocket JSON subprotocols.

        """
        headers = []
        # https://tools.ietf.org/html/rfc6455
        headers.append("GET /{} HTTP/1.1".format(self.websocket_location))
        headers.append("Host: {}".format(self.host))
        headers.append("Upgrade: websocket")
        headers.append("Connection: Upgrade")
        # Sec-WebSocket-Key header containing base64-encoded random bytes,
        # and the server replies with a hash of the key in the
        # Sec-WebSocket-Accept header. This is intended to prevent a caching
        # proxy from re-sending a previous WebSocket conversation and does not
        # provide any authentication, privacy or integrity
        headers.append("Sec-WebSocket-Key: {}".format(self.key))
        headers.append("Origin: wss://{}".format(self.host))
        headers.append("Sec-WebSocket-Version: {}".format(WEBSOCKET_VERSION))
        headers.append("Sec-WebSocket-Protocol: {}".format(
            WEBSOCKET_SUBPROTOCOLS))

        return headers

    def _read_handshake_response(self):
        status = None
        headers = {}

        while True:
            line = self._recv_handshake_response_by_line()

            try:
                line = line.decode('utf-8')
            except:
                line = u'{}'.format(line)

            if line == "\r\n" or line == "\n":
                break

            line = line.strip()
            if line == '':
                continue

            if not status:
                status_info = line.split(" ", 2)
                try:
                    status = int(status_info[1])
                except IndexError:
                    logger.warning('unexpected handshake resposne')
                    logger.error('%s', status_info)
                    raise

                headers['status_info'] = status_info
                headers['status'] = status
                continue

            kv = line.split(":", 1)
            if len(kv) != 2:
                raise Exception(
                    'Invalid header: "{}"'.format(line)
                )

            key, value = kv
            headers[key.lower()] = value.strip().lower()

        return status, headers

    def _recv_handshake_response_by_line(self):
        received_bytes = bytearray()

        while True:
            bytes = self.socket.recv(bufsize=1)

            if not bytes:
                break

            received_bytes.append(bytes)

            if bytes == "\n" or bytes == "\r\n":
                # a complete line has been received
                break

        return received_bytes

    def connect(self):
        self._connect()
        self._upgrade()

    def send(self, message):
        self.socket.sendall(message)
        logger.info('sent message: "%s"', message)

    def read_websocket_frame(self, bufsize=1):
        logger.debug('read a WebSocket frame')
        frame = None
        received_bytes = bytearray()

        while True:
            try:
                bytes = self.socket.recv(bufsize)
            except greenlet.GreenletExit as exc:
                raise ConnectionError('Connection closed: "{}"'.format(exc))
            except socket.timeout as e:
                message = str(e)
                raise ConnectionError('timeout: "{}"'.format(message))
            except Exception as exc:
                raise ConnectionError('error: "{}"'.format(exc))

            if not bytes:
                break

            received_bytes.extend(bytes)

            try:
                frame = ServerFrame(received_bytes)
            except IncompleteFrameError as exc:
                # this is totallt expecteda and we let it silently pass
                pass
            else:
                break

        if frame is None:
            raise WampProtocolError("No frame returned")
        logger.debug('return complete Frame')
        return frame

    def send_websocket_frame(self, message):
        frame = ClientFrame(message)
        self.socket.sendall(frame.payload)


class TLSWebSocket(WebSocket):
    def __init__(
            self, host, port, websocket_location, certificate,
            ssl_version=None,
    ):
        self.host = host
        self.port = port
        self.websocket_location = websocket_location.lstrip('/')
        if ssl_version:
            self.ssl_version = ssl_version
        elif hasattr(ssl,'PROTOCOL_TLSv1_2'):
            self.ssl_version = ssl_version or ssl.PROTOCOL_TLSv1_2
        else:
            self.ssl_version = ssl_version or ssl.PROTOCOL_TLSv1
        self.key = encodestring(uuid.uuid4().bytes).decode('utf-8').strip()
        self.certificate = certificate

        self.buffersize = 1
        self.socket = None
        logger.info("websocket location: %s", websocket_location)

    def _connect(self):
        _socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _socket.setsockopt(ssl.SOL_SOCKET, socket.SO_RCVBUF, self.buffersize)
        _socket.setsockopt(ssl.SOL_SOCKET, socket.SO_SNDBUF, self.buffersize)

        logger.debug("wrapping socker in TLS")
        _socket = ssl.wrap_socket(
            _socket,
            ssl_version=self.ssl_version,
            ciphers="ECDH+AESGCM:DH+AESGCM:ECDH+AES256:DH+AES256:ECDH+AES128:\
            DH+AES:ECDH+3DES:DH+3DES:RSA+AES:RSA+3DES:!ADH:!AECDH:!MD5:!DSS",
            cert_reqs=ssl.CERT_REQUIRED,
            ca_certs=self.certificate,
        )

        try:
            logger.debug("connectiing")
            _socket.connect((self.host, self.port))
        except socket_error as exc:
            if exc.errno == 61:
                logger.error(
                    'unable to connect to %s:%s', self.host, self.port
                )

            raise

        self.socket = _socket

    def _recv_handshake_response_by_line(self):
        received_bytes = bytearray()

        while True:
            bytes = self.socket.recv(1)

            if not bytes:
                break

            received_bytes.append(bytes)

            if bytes == "\n" or bytes == "\r\n":
                # a complete line has been received
                break

        return received_bytes
