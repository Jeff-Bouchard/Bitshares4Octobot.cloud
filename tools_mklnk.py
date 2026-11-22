"""Write a Windows .lnk shortcut. Pure stdlib, no COM, no PowerShell.

Follows MS-SHLLINK, the published Shell Link Binary File Format. Only the
parts a launcher needs are emitted: the header, a LinkInfo naming the target
on a local drive, and the string section holding the working directory,
arguments and icon.

    python mklnk.py <output.lnk> <target.exe> [arguments] [working dir] [description]
"""

import struct
import sys

HEADER_SIZE = 0x4C
LINK_CLSID = bytes([0x01, 0x14, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00,
                    0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46])

HAS_NAME = 0x00000004
HAS_LINK_INFO = 0x00000002
HAS_WORKING_DIR = 0x00000010
HAS_ARGUMENTS = 0x00000020
IS_UNICODE = 0x00000080

FILE_ATTRIBUTE_NORMAL = 0x00000080
SW_SHOWNORMAL = 1
DRIVE_FIXED = 3


def utf16_string(text):
    """A StringData entry: character count, then UTF-16LE, no terminator."""
    encoded = text.encode("utf-16-le")
    return struct.pack("<H", len(encoded) // 2) + encoded


def link_info(target):
    """LinkInfo with a VolumeID and a local base path.

    Windows resolves the shortcut from this path, so it must be the native
    form (C:\\folder\\program.exe), not a Git Bash /c/folder path.
    """
    base_path = target.encode("ascii", "replace") + b"\x00"
    volume_label = b"\x00"                      # no label; offset still required
    volume_id = struct.pack("<IIII", 16 + len(volume_label), DRIVE_FIXED, 0, 0x10) + volume_label

    header_size = 0x1C
    volume_id_offset = header_size
    local_base_path_offset = volume_id_offset + len(volume_id)
    common_path_suffix_offset = local_base_path_offset + len(base_path)
    total = common_path_suffix_offset + 1       # the suffix is a lone NUL

    return (struct.pack("<IIIIIII",
                        total,
                        header_size,
                        0x00000001,              # VolumeIDAndLocalBasePath
                        volume_id_offset,
                        local_base_path_offset,
                        0,                       # no network relative link
                        common_path_suffix_offset)
            + volume_id + base_path + b"\x00")


def build(target, arguments="", working_dir="", description=""):
    flags = HAS_LINK_INFO | IS_UNICODE
    if description:
        flags |= HAS_NAME
    if working_dir:
        flags |= HAS_WORKING_DIR
    if arguments:
        flags |= HAS_ARGUMENTS

    header = (struct.pack("<I", HEADER_SIZE)
              + LINK_CLSID
              + struct.pack("<I", flags)
              + struct.pack("<I", FILE_ATTRIBUTE_NORMAL)
              + struct.pack("<Q", 0)            # creation time
              + struct.pack("<Q", 0)            # access time
              + struct.pack("<Q", 0)            # write time
              + struct.pack("<I", 0)            # file size
              + struct.pack("<i", 0)            # icon index
              + struct.pack("<I", SW_SHOWNORMAL)
              + struct.pack("<H", 0)            # hot key
              + struct.pack("<H", 0)            # reserved
              + struct.pack("<I", 0)            # reserved
              + struct.pack("<I", 0))           # reserved
    assert len(header) == HEADER_SIZE, len(header)

    out = header + link_info(target)
    # StringData follows the order the specification fixes, not the order the
    # flags were set in.
    if description:
        out += utf16_string(description)
    if working_dir:
        out += utf16_string(working_dir)
    if arguments:
        out += utf16_string(arguments)
    return out + struct.pack("<I", 0)           # terminal block


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    path = sys.argv[1]
    target = sys.argv[2]
    arguments = sys.argv[3] if len(sys.argv) > 3 else ""
    working_dir = sys.argv[4] if len(sys.argv) > 4 else ""
    description = sys.argv[5] if len(sys.argv) > 5 else ""
    with open(path, "wb") as handle:
        handle.write(build(target, arguments, working_dir, description))
    return 0


if __name__ == "__main__":
    sys.exit(main())
