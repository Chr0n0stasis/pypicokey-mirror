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

import sys
import hashlib

try:
    from cvc.asn1 import ASN1
except ModuleNotFoundError:
    print('ERROR: cvc module not found! Install pycvc package.\nTry with `pip install pycvc`')
    sys.exit(-1)

try:
    from cryptography.hazmat.primitives import cmac
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
except ModuleNotFoundError:
    print('ERROR: cryptography module not found! Install cryptography package.\nTry with `pip install cryptography`')
    sys.exit(-1)


class SecureChannel:
    OID_ID_CA_ECDH_AES_CBC_CMAC_128 = b'\x04\x00\x7F\x00\x07\x02\x02\x03\x02\x02'
    BLOCK_SIZE = 16

    PROTO_OID = OID_ID_CA_ECDH_AES_CBC_CMAC_128

    def __init__(self, shared=None, nonce=None):
        self.__derive_sm_keys(shared=shared, nonce=nonce)

    def __derive_sm_key(input=None, counter=0, nonce=None):
        b = b''
        if (input):
            b += input
        if (nonce):
            b += nonce
        b += counter.to_bytes(4, 'big')
        digest = hashlib.sha1(b).digest()
        return digest[:16]

    def __derive_sm_keys(self, shared, nonce):
        self.__sm_kenc = SecureChannel.__derive_sm_key(shared, 1, nonce)
        self.__sm_kmac = SecureChannel.__derive_sm_key(shared, 2, nonce)
        self.__sm_counter = 0

    def __sm_sign(self, data):
        c = cmac.CMAC(algorithms.AES(self.__sm_kmac))
        c.update(data)
        return c.finalize()

    def __sm_inc_counter(self):
        self.__sm_counter += 1

    def __sm_iv(self):
        iv = b'\x00'*16
        cipher = Cipher(algorithms.AES(self.__sm_kenc), modes.CBC(iv))
        encryptor = cipher.encryptor()
        message = self.__sm_counter.to_bytes(self.BLOCK_SIZE, 'big')
        ct = encryptor.update(message) + encryptor.finalize()
        return ct

    def verify_token(self, token, pbkey):
        a = ASN1().add_tag(0x7F49, ASN1().add_oid(self.PROTO_OID).add_tag(0x86, pbkey).encode())
        signature = self.__sm_sign(a.encode())
        return signature[:len(token)] == token

    def wrap_apdu(self, apdu):
        cla, ins, p1, p2, lc, data, le = apdu[0], apdu[1], apdu[2], apdu[3], apdu[4:7], apdu[7:-2], apdu[-2:]
        cla |= 0x0C

        data += [0x80]
        data += [0x00] * (self.BLOCK_SIZE - (len(data) % self.BLOCK_SIZE))

        self.__sm_inc_counter()
        iv = self.__sm_iv()
        cipher = Cipher(algorithms.AES(self.__sm_kenc), modes.CBC(iv))
        encryptor = cipher.encryptor()
        ct = encryptor.update(bytes(data)) + encryptor.finalize()
        if (ins & 0x1 == 0):
            tlv_body = [0x01] + list(ct)
            body = ASN1().add_tag(0x87, tlv_body).encode()
        else:
            body = ASN1().add_tag(0x85, list(ct)).encode()
        do_le = [0x97, 0x02] + le

        macb = list(self.__sm_counter.to_bytes(self.BLOCK_SIZE, 'big')) + [cla, ins, p1, p2, 0x80] + [0x00] * (self.BLOCK_SIZE - 5) + list(body) + do_le + [0x80]
        macb += [0x00] * (self.BLOCK_SIZE - (len(macb) % self.BLOCK_SIZE))
        macc = self.__sm_sign(bytes(macb))
        do_mac = ASN1().add_tag(0x8E, list(macc)).encode()

        new_lc = list((len(body) + len(do_le) + len(do_mac)).to_bytes(3, 'big'))

        apdu = [cla, ins, p1, p2] + new_lc + list(body) + do_le + list(do_mac) + [0x00, 0x00]
        return apdu

    def unwrap_rapdu(self, apdu):
        self.__sm_inc_counter()
        signature = ASN1().decode(apdu).find(0x8E).data()
        body = ASN1().decode(apdu).find(0x87)
        sw = ASN1().decode(apdu).find(0x99)
        if (not sw):
            raise ValueError("SM: no sw found")
        sw = sw.data()
        do_sw = ASN1.make_tag(0x99, sw)
        macb = bytearray(self.__sm_counter.to_bytes(self.BLOCK_SIZE, 'big'))
        if (body):
            body = body.data()
            if (body and body[0] != 0x1):
                raise ValueError("SM: data not consistent")
            do_body = ASN1.make_tag(0x87, body)
            macb += do_body
        macb += do_sw
        macb += bytearray([0x80])
        macb += bytearray([0x00] * (self.BLOCK_SIZE - (len(macb) % self.BLOCK_SIZE)))
        sign = self.__sm_sign(bytes(macb))[:len(signature)]
        if (signature != sign):
            raise ValueError("SM: signature mismatch")
        rapdu = []
        if (body):
            body = body[1:]
            iv = self.__sm_iv()
            cipher = Cipher(algorithms.AES(self.__sm_kenc), modes.CBC(iv))
            decryptor = cipher.decryptor()
            ct = decryptor.update(bytes(body)) + decryptor.finalize()
            l = len(ct) - 1
            while (l >= 0 and ct[l] == 0x00):
                l -= 1
            if (l < 0 or ct[l] != 0x80):
                raise ValueError("SM: body malformed")
            rapdu = list(ct[:l])
        return rapdu, sw[0] << 8 | sw[1]

