"""_ImplicitFTPTLS — the two Bambu FTPS quirks, each of which cost a spike to pin down.

``ftplib`` speaks *explicit* FTPS (plaintext greeting, then ``AUTH TLS``); Bambu speaks
*implicit* FTPS on port 990. And Bambu's data channel requires TLS **session resumption** from
the control connection, or the transfer stalls. Both are handled here and explained where they
bite. See scripts/check_ftps_integrity.py for the live round-trip check.
"""

from __future__ import annotations

import ftplib
import logging
import ssl
from collections.abc import Callable

log = logging.getLogger("amsx.system.infra.ftps")

__all__ = ["_ImplicitFTPTLS"]


class _ImplicitFTPTLS(ftplib.FTP_TLS):
    """``ftplib`` speaks *explicit* FTPS (plaintext greeting, then ``AUTH TLS``); Bambu speaks
    *implicit* FTPS — the control channel is TLS from the first byte on port 990. We wrap the
    control socket in TLS the moment ``ftplib`` assigns it, which turns the explicit client
    into an implicit one without touching the rest of the state machine.

    Bambu's FTPS ALSO requires **TLS session resumption on the data channel**: each PASV data
    connection must reuse the control connection's TLS session, or the encrypted transfer stalls
    and reads time out (the file may still arrive, but ftplib raises). ``ntransfercmd`` below
    wraps every data socket reusing ``self.sock.session`` to satisfy that.

    Finally, Bambu never answers the data-channel **close_notify**, so the TLS shutdown that
    ftplib's stock ``storbinary`` performs after an upload blocks until the socket timeout and
    raises ``TimeoutError`` — though the file already committed and the server already sent 226.
    Our ``storbinary`` override skips that shutdown (plain close); verified live (ftps_diag.py).
    """

    @property
    def sock(self) -> object:
        return self._sock

    @sock.setter
    def sock(self, value: object) -> None:
        if value is not None and not isinstance(value, ssl.SSLSocket):
            value = self.context.wrap_socket(value)
        self._sock = value

    def ntransfercmd(self, cmd: str, rest: object = None):
        # Open the data connection, then (when PROT P is active) TLS-wrap it REUSING the control
        # channel's session — the resumption Bambu's server demands. Without `session=...` the
        # data transfer hangs -> "read operation timed out".
        conn, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(
                conn, server_hostname=self.host, session=self.sock.session
            )
        return conn, size

    def storbinary(  # type: ignore[override]
        self,
        cmd: str,
        fp: object,
        blocksize: int = 8192,
        callback: Callable[[bytes], object] | None = None,
        rest: object = None,
    ) -> str:
        # Run the STOR ourselves and SKIP the post-transfer ``conn.unwrap()``. Both
        # ``ftplib.FTP.storbinary`` AND ``FTP_TLS.storbinary`` perform that TLS shutdown
        # handshake on the data socket — and Bambu's FTPS server never answers the close_notify,
        # so ``unwrap()`` blocks until the socket timeout and raises ``TimeoutError`` ("read
        # operation timed out") EVEN THOUGH the file already committed and the server already
        # sent 226. Verified live on the A1 mini (see scripts/check_ftps_integrity.py): a
        # plain socket close commits the upload and returns 226 in ~0.1s. The data channel is
        # still TLS (via our session-reusing ``ntransfercmd``) — we only drop the redundant
        # TLS *shutdown*.
        self.voidcmd("TYPE I")
        with self.transfercmd(cmd, rest) as conn:
            while True:
                buf = fp.read(blocksize)  # type: ignore[attr-defined]
                if not buf:
                    break
                conn.sendall(buf)
                if callback is not None:
                    callback(buf)
        return self.voidresp()
