"""The OctoBot side of the BitShares DEX exchange.

OctoBot picks an exchange class by walking the subclasses of RestExchange and
asking each one whether it supports the configured name. Declaring one here
means OctoBot uses this tentacle rather than falling through to its generic
DefaultRestExchange, which in turn means the exchange shows up by name in the
interface and can carry its own settings later.

The heavy lifting is in ccxt_bitshares_dex.py: OctoBot drives everything
through the ccxt (CryptoCurrency eXchange Trading library) connector, so there
is very little left to do at this level.
"""

import octobot_trading.exchanges as exchanges


class BitsharesDex(exchanges.RestExchange):
    DESCRIPTION = (
        "BitShares DEX (Decentralised EXchange). Prices, order books and "
        "candles are read straight from a BitShares (Graphene) node over "
        "HTTPS. Placing orders additionally requires the local signing bridge."
    )

    @classmethod
    def get_name(cls):
        return "bitshares_dex"

    @classmethod
    def is_configurable(cls):
        return True

    def get_additional_connector_config(self):
        # Nothing to add: the ccxt class reads BITSHARES_CCXT_BRIDGE_URL and
        # BRIDGE_TOKEN from the environment itself, so the key never passes
        # through OctoBot's configuration files.
        return {}
