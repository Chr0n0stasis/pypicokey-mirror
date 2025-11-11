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

class SWCodes:
    SW_BYTES_REMAINING_00               = 0x6100
    SW_WARNING_STATE_UNCHANGED          = 0x6200
    SW_WARNING_CORRUPTED                = 0x6281
    SW_WARNING_EOF                      = 0x6282
    SW_WARNING_EF_DEACTIVATED           = 0x6283
    SW_WARNING_WRONG_FCI                = 0x6284
    SW_WARNING_EF_TERMINATED            = 0x6285

    SW_WARNING_NOINFO                   = 0x6300
    SW_WARNING_FILLUP                   = 0x6381

    SW_EXEC_ERROR                       = 0x6400

    SW_SECURE_MESSAGE_EXEC_ERROR        = 0x6600

    SW_WRONG_LENGTH                     = 0x6700
    SW_WRONG_DATA                       = 0x6700

    SW_LOGICAL_CHANNEL_NOT_SUPPORTED    = 0x6881
    SW_SECURE_MESSAGING_NOT_SUPPORTED   = 0x6882

    SW_COMMAND_INCOMPATIBLE             = 0x6981
    SW_SECURITY_STATUS_NOT_SATISFIED    = 0x6982
    SW_PIN_BLOCKED                      = 0x6983
    SW_DATA_INVALID                     = 0x6984
    SW_CONDITIONS_NOT_SATISFIED         = 0x6985
    SW_COMMAND_NOT_ALLOWED              = 0x6986
    SW_SECURE_MESSAGING_MISSING_DO      = 0x6987
    SW_SECURE_MESSAGING_INCORRECT_DO    = 0x6988
    SW_APPLET_SELECT_FAILED             = 0x6999

    SW_INCORRECT_PARAMS                 = 0x6A80
    SW_FUNC_NOT_SUPPORTED               = 0x6A81
    SW_FILE_NOT_FOUND                   = 0x6A82
    SW_RECORD_NOT_FOUND                 = 0x6A83
    SW_FILE_FULL                        = 0x6A84
    SW_WRONG_NE                         = 0x6A85
    SW_INCORRECT_P1P2                   = 0x6A86
    SW_WRONG_NC                         = 0x6A87
    SW_REFERENCE_NOT_FOUND              = 0x6A88
    SW_FILE_EXISTS                      = 0x6A89

    SW_WRONG_P1P2                       = 0x6B00

    SW_CORRECT_LENGTH_00                = 0x6C00

    SW_INS_NOT_SUPPORTED                = 0x6D00

    SW_CLA_NOT_SUPPORTED                = 0x6E00

    SW_UNKNOWN                          = 0x6F00

    SW_OK                               = 0x9000
