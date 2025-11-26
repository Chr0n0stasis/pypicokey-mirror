"""
/*
 * This file is part of the pypicokey distribution (https://github.com/polhenarejos/pypicokey).
 * Copyright (c) 2025 Pol Henarejos.
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as published by
 * the Free Software Foundation, version 3.
 *
 * This program is distributed in the hope that it will be useful, but
 * WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
 * Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with this program. If not, see <https://www.gnu.org/licenses/>.
 */
"""

from typing import Optional
import threading
from .APDU import APDUResponse
from .SecureChannel import SecureChannel
from .RescuePicoKey import RescuePicoKey
from .RescueMonitor import RescueMonitor, RescueMonitorObserver
from .PhyData import PhyData
from .core import NamedIntEnum
import usb.core
from .core.log import get_logger

logger = get_logger("PicoKey")

class Platform(NamedIntEnum):
    RP2040 = 0
    RP2350 = 1
    ESP32  = 2
    EMULATION = 3

class Product(NamedIntEnum):
    UNKNOWN = 0
    HSM     = 1
    FIDO    = 2
    OPENPGP = 3

class ConnectionType(NamedIntEnum):
    UNKNOWN = 0
    SMARTCARD = 1
    RESCUE = 2

class ConnectTimeout(Exception):
    pass

def connect_with_timeout(connection, timeout=2.0):
    result = {}

    def worker():
        try:
            connection.connect()
            result["ok"] = True
        except Exception as e:
            result["error"] = e

    t = threading.Thread(target=worker)
    t.daemon = True
    t.start()
    t.join(timeout)

    if t.is_alive():
        raise ConnectTimeout("connection.connect() timed out")

    if "error" in result:
        raise result["error"]

    return True

class PicoKey:

    def __init__(self, slot=-1, force_rescue=False):
        logger.debug("Initializing PicoKey...")
        self.__apdu = []
        self.__connection_type = ConnectionType.UNKNOWN
        self.__monitor = None
        self.__observer = None
        self.__sc = None
        self.__card = None

        if (not force_rescue):
            from smartcard.System import readers
            import smartcard.Exceptions
            from smartcard.CardMonitoring import CardMonitor, CardObserver
            logger.debug("Searching for smartcard readers...")
            class PicoCardObserver(CardObserver):
                def __init__(self, device):
                    self.__device = device

                def update(self, observable, actions):
                    (added, removed) = actions
                    if added:
                        pass
                    if removed:
                        self.__device.close()

            def reader_has_card(reader):
                try:
                    connection = reader.createConnection()
                    connect_with_timeout(connection, timeout=1.0)
                    return connection
                except smartcard.Exceptions.NoCardException:
                    return None
                return None

            logger.debug("Checking available smartcard readers...")
            try:
                rdrs = readers()
            except Exception as e:
                logger.error("Error accessing smartcard readers: " + str(e))
                rdrs = []
            if len(rdrs) > 0:
                if (slot >= 0 and slot >= len(rdrs)):
                    logger.error("Slot number out of range")
                    raise Exception('Slot number out of range')

                if (slot >= 0 and slot < len(rdrs)):
                    logger.debug(f"Checking reader slot {slot}")
                    reader = rdrs[slot]
                    connection = reader_has_card(reader)
                    if (connection is None):
                        logger.error(f"No card in reader slot {slot}")
                        raise Exception(f'No card in reader slot {slot}')
                    self.__card = connection
                else:
                    for i, reader in enumerate(rdrs):
                        reader = rdrs[i]
                        connection = reader_has_card(reader)
                        if (connection is None):
                            continue
                        logger.debug(f"Card found in reader slot {i}")
                        self.__card = connection
                        self.__connection_type = ConnectionType.SMARTCARD

                        logger.debug("Setting up card monitor...")
                        self.__monitor = CardMonitor()
                        logger.debug("Creating card observer...")
                        self.__observer = PicoCardObserver(self)
                        logger.debug("Adding observer to monitor...")
                        self.__monitor.addObserver(self.__observer)
                        logger.debug("Observer added to monitor")
                        break

        if (self.__card is None):
            logger.debug("Attempting to connect in rescue mode...")
            class PicoRescueObserver(RescueMonitorObserver):
                def __init__(self, device):
                    self.__device = device

                def update(self, actions: tuple[Optional[usb.core.Device], Optional[usb.core.Device]]):
                    (connected, disconnected) = actions
                    if connected:
                        pass
                    if disconnected:
                        self.__device.close()
            try:
                self.__card = RescuePicoKey()
                logger.debug("Rescue mode card initialized")
                self.__connection_type = ConnectionType.RESCUE
                logger.debug("Setting up rescue monitor...")
                self.__observer = PicoRescueObserver(self)
                logger.debug("Creating rescue monitor...")
                self.__monitor = RescueMonitor(device=self.__card, cls_callback=self.__observer)
            except Exception:
                logger.error("No PicoKey device detected")
                raise Exception('time-out: no card inserted')
        try:
            logger.debug("Selecting applet in rescue mode...")
            resp, sw1, sw2 = self.select_applet(rescue=True)
            logger.debug(f"Applet selected with response code: 0x{sw1:02X}{sw2:02X}")
            if (sw1 == 0x90 and sw2 == 0x00):
                self.platform = Platform(resp[0])
                self.product = Product(resp[1])
                self.version = (resp[2], resp[3])
        except APDUResponse:
            logger.error("APDU response error during applet selection")
            self.platform = Platform(Platform.RP2040)
            self.product = Product(Product.UNKNOWN)
            self.version = (0, 0)

    @property
    def device(self):
        return self.__card

    def has_device(self):
        return self.__card is not None

    @property
    def connection_type(self):
        return self.__connection_type

    def close(self):
        logger.debug("Closing device...")
        if (not self.__card):
            logger.debug("No device to close")
            return
        if isinstance(self.__card, RescuePicoKey):
            logger.debug("Stopping rescue monitor...")
            self.__monitor.stop()
            self.__monitor = None
            self.__observer = None
            self.__card.close()
        else:
            logger.debug("Removing card monitor observer...")
            self.__monitor.deleteObserver(self.__observer)
            self.__observer = None
            self.__monitor = None
            logger.debug("Disconnecting and releasing card...")
            self.__card.disconnect()
            logger.debug("Card disconnected")
            self.__card.release()
        self.__card = None

    def transmit(self, apdu: list[int]):
        if (not self.__card):
            logger.error("No device connected")
            raise Exception('No device connected')
        response, sw1, sw2 = self.__card.transmit(apdu)
        return response, sw1, sw2

    def send(self, command: int, cla: int = 0x00, p1: int =0x00, p2: int=0x00, ne : Optional[int] = None, data : Optional[list[int]] = None, codes : list[int] = []):
        logger.debug(f"Sending command {hex(command)} with cla={hex(cla)}, p1={hex(p1)}, p2={hex(p2)}, ne={ne}")
        if (not self.__card):
            logger.error("No device connected")
            raise Exception('No device connected')
        lc = []
        dataf = []
        if (data):
            lc = [0x00] + list(len(data).to_bytes(2, 'big'))
            dataf = list(data)
        else:
            lc = [0x00*3]
        if (ne is None):
            le = [0x00, 0x00]
        else:
            le = list(ne.to_bytes(2, 'big'))
        if (isinstance(command, list) and len(command) > 1):
            apdu = command
        else:
            apdu = [cla, command]

        apdu = apdu + [p1, p2] + lc + dataf + le
        self.__apdu = apdu
        logger.trace(f"APDU -> {' '.join([f'{x:02X}' for x in apdu])}")
        if (self.__sc):
            apdu = self.__sc.wrap_apdu(apdu)
            logger.trace(f"Wrapped APDU -> {' '.join([f'{x:02X}' for x in apdu])}")

        try:
            response, sw1, sw2 = self.__card.transmit(apdu)
        except Exception:
            logger.debug("Reconnecting card after transmit failure")
            self.__card.reconnect()
            try:
                response, sw1, sw2 = self.__card.transmit(apdu)
            except Exception as e:
                logger.error("APDU transmission error after reconnect: " + str(e))
                raise Exception("APDU transmission error after reconnect: " + str(e))

        code = (sw1<<8|sw2)
        if (sw1 != 0x90):
            if (sw1 == 0x63 and sw2 & 0xF0 == 0xC0):
                pass
            # elif (code == 0x6A82):
            #     self.select_applet()
            #     if (sw1 == 0x90):
            #         response, sw1, sw2 = self.__card.transmit(apdu)
            #         if (sw1 == 0x90):
            #             return response
            elif (sw1 == 0x61):
                response = []
                while (sw1 == 0x61):
                    apdu = [0x00, 0xC0, 0x00, 0x00, sw2]
                    resp, sw1, sw2 = self.__card.transmit(apdu)
                    response += resp
                code = (sw1<<8|sw2)
            if (code not in codes and code != 0x9000):
                raise APDUResponse(sw1, sw2)
        logger.trace(f"Response APDU <- {' '.join([f'{x:02X}' for x in response])}, SW1={sw1:02X}, SW2={sw2:02X}")
        if (self.__sc):
            response, code = self.__sc.unwrap_rapdu(response)
            logger.trace(f"Unwrapped RAPDU <- {' '.join([f'{x:02X}' for x in response])}, Code={code:04X}")
            if (code not in codes and code != 0x9000):
                raise APDUResponse(code >> 8, code & 0xff)
        return bytes(response), code

    def resend(self):
        apdu = self.__apdu
        if (self.__sc):
            apdu = self.__sc.wrap_apdu(apdu)

        try:
            response, sw1, sw2 = self.__card.transmit(apdu)
        except Exception:
            logger.debug("Reconnecting card after transmit failure")
            self.__card.reconnect()
            response, sw1, sw2 = self.__card.transmit(apdu)

        return bytes(response), sw1, sw2

    def open_secure_channel(self, shared: bytes, nonce: bytes, token: bytes, pbkeyBytes: bytes):
        logger.debug("Opening secure channel")
        sc = SecureChannel(shared=shared, nonce=nonce)
        res = sc.verify_token(token, pbkeyBytes)
        if (not res):
            raise Exception('Secure Channel token verification failed')
        self.__sc = sc

    def select_applet(self, rescue : bool = False):
        if (rescue):
            logger.debug("Selecting rescue applet")
            return self.transmit([0x00, 0xA4, 0x04, 0x04, 0x08, 0xA0, 0x58, 0x3F, 0xC1, 0x9B, 0x7E, 0x4F, 0x21, 0x00])
        logger.debug("Selecting standard applet")
        return self.transmit([0x00, 0xA4, 0x04, 0x00, 0x0B, 0xE8, 0x2B, 0x06, 0x01, 0x04, 0x01, 0x81, 0xC3, 0x1F, 0x02, 0x01, 0x00])

    def phy(self, data : Optional[list[int]] = None):
        if (data is None):
            try:
                resp, sw = self.send(0x1E, cla=0x80, p1=0x00, ne=256)
                return PhyData.parse(resp)
            except Exception:
                pass
            return None
        else:
            self.send(0x1C, cla=0x80, p1=0x01, data=data)

    def flash_info(self):
        logger.debug("Retrieving flash info")
        try:
            resp, sw = self.send(0x1E, cla=0x80, p1=0x02)
            free = int.from_bytes(resp[0:4], 'big')
            used = int.from_bytes(resp[4:8], 'big')
            total = int.from_bytes(resp[8:12], 'big')
            nfiles = int.from_bytes(resp[12:16], 'big')
            size = int.from_bytes(resp[16:20], 'big')
        except Exception:
            free = used = total = nfiles = size = 0
        return {
            'free': free,
            'used': used,
            'total': total,
            'nfiles': nfiles,
            'size': size
        }

    def secure_info(self):
        logger.debug("Retrieving secure boot info")
        resp, sw = self.send(0x1E, cla=0x80, p1=0x03)
        return {
            'enabled': resp[0] != 0,
            'locked': resp[1] != 0,
            'boot_key': resp[2]
        }

    def secure_boot(self, bootkey_index: int = 0, lock: bool = False):
        logger.debug(f"Setting secure boot: bootkey_index={bootkey_index}, lock={lock}")
        data = bytes([bootkey_index & 0xFF, 1 if lock else 0])
        self.send(0x1C, cla=0x80, p1=0x02, data=data)
