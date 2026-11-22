"""BitShares DEX (Decentralised EXchange) as an OctoBot tentacle.

This folder lives entirely inside your own OctoBot installation, under
tentacles/Trading/Exchange/. Nothing is written to Python's site-packages and
no file belonging to OctoBot itself is modified. Deleting this folder removes
the exchange completely.

Two things happen when OctoBot loads this tentacle, in this order:

1. ccxt (CryptoCurrency eXchange Trading library) is taught about an exchange
   called `bitshares_dex`. OctoBot resolves every exchange through
   `getattr(ccxt.async_support, name)`, and lists the ones it can offer from
   `set(ccxt.exchanges)`, so the class has to be attached to both modules
   before any exchange is created. Tentacles load long before that, which is
   why this works from here rather than from an interpreter-level hook.

2. The OctoBot exchange class itself is exported, so OctoBot finds a real
   named tentacle instead of falling back to its generic implementation.
"""

import ccxt
import ccxt.async_support as ccxt_async

from .ccxt_bitshares_dex import bitshares_dex as _ccxt_class


def _register(module, name="bitshares_dex"):
    """Attach the class to a ccxt module. Idempotent: a second tentacle load,
    or a reload during development, must not duplicate the exchange name."""
    setattr(module, name, _ccxt_class)
    known = getattr(module, "exchanges", None)
    if isinstance(known, list) and name not in known:
        known.append(name)


_register(ccxt_async)
_register(ccxt)

from .bitshares_dex_exchange import BitsharesDex  # noqa: E402  — must follow registration

__all__ = ["BitsharesDex"]
