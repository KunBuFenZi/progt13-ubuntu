# SPDX-License-Identifier: GPL-2.0-only
"""Which ABL overlay sink layout a packaging DTB carries, read from the DTB.

tools/build-erhai-abl-symbols.py places the inert overlay sink in one of two
layouts:

* contained (the default): /erhai-abl/overlay-sink inside a disabled
  container.  The sink never becomes a device, so rpmhpd, the NoCs and the
  PSCI power domains reach sync_state().  This is the layout daily
  deliveries use.
* legacy (--legacy-sink): the root child /erhai-abl-overlay-sink, the
  layout the installed releases before 0.1.56 boot with.  The merged sink
  becomes a platform device that never binds and holds back sync_state()
  of those providers; it is kept only as a fallback and for comparison
  images.

The boot image builders take a finished DTB, so they read the layout back
from the DTB itself rather than trusting a flag: a legacy DTB is refused
unless --legacy-sink says it is meant, and an explicit --legacy-sink or
--contained-sink is refused on a DTB that carries anything else.  The
layout goes into their manifests.
"""
import struct

LEGACY = 'legacy'
CONTAINED = 'contained'
NONE = 'none'  # no sink at all: a plain mainline DTB
LAYOUTS = (LEGACY, CONTAINED)
ROOT_NODES = {'erhai-abl-overlay-sink': LEGACY, 'erhai-abl': CONTAINED}
USE = {
    CONTAINED: 'default: daily deliveries; the sink never becomes a device',
    LEGACY: 'opt-in (--legacy-sink): fallback and comparison only, holds back sync_state()',
    NONE: 'no ABL overlay sink (plain mainline DTB)',
}

FDT_MAGIC = 0xd00dfeed
FDT_BEGIN_NODE, FDT_END_NODE, FDT_PROP, FDT_NOP, FDT_END = 1, 2, 3, 4, 9


class LayoutError(ValueError):
    pass


def _align4(value):
    return (value + 3) & ~3


def root_children(blob):
    """Names of the root node's direct children in a flattened device tree."""
    if len(blob) < 40 or struct.unpack('>I', blob[:4])[0] != FDT_MAGIC:
        raise LayoutError('not a flattened device tree')
    total, off_struct = struct.unpack('>II', blob[4:12])
    size_struct = struct.unpack('>I', blob[36:40])[0]
    if total > len(blob) or off_struct + size_struct > total:
        raise LayoutError('device tree header points past the blob')
    pos, end = off_struct, off_struct + size_struct
    depth, names = 0, []
    while pos + 4 <= end:
        token = struct.unpack('>I', blob[pos:pos + 4])[0]
        pos += 4
        if token == FDT_BEGIN_NODE:
            stop = blob.index(b'\0', pos, end)
            depth += 1
            if depth == 2:
                names.append(blob[pos:stop].decode('ascii', 'replace'))
            pos = _align4(stop + 1)
        elif token == FDT_END_NODE:
            depth -= 1
            if depth < 0:
                raise LayoutError('unbalanced device tree structure')
        elif token == FDT_PROP:
            length = struct.unpack('>I', blob[pos:pos + 4])[0]
            pos = _align4(pos + 8 + length)
        elif token == FDT_NOP:
            continue
        elif token == FDT_END:
            return names
        else:
            raise LayoutError(f'unknown device tree token {token:#x}')
    raise LayoutError('device tree structure has no end token')


def sink_layout(blob):
    """'legacy', 'contained' or 'none' for a DTB blob; both at once is refused."""
    found = {ROOT_NODES[name] for name in root_children(blob) if name in ROOT_NODES}
    if len(found) > 1:
        raise LayoutError('the DTB carries both sink layouts')
    return found.pop() if found else NONE


def vendor_boot_dtb(image):
    """The DTB section of an Android vendor_boot image (header v3/v4)."""
    if image[:8] != b'VNDRBOOT':
        raise LayoutError('not a vendor_boot image')
    version, page = struct.unpack('<II', image[8:16])
    if version not in (3, 4) or page == 0:
        raise LayoutError(f'unsupported vendor_boot header v{version}, page size {page}')
    ramdisk_size = struct.unpack('<I', image[24:28])[0]
    header_size, dtb_size = struct.unpack('<II', image[2096:2104])

    def pages(size):
        return (size + page - 1) // page * page

    start = pages(header_size) + pages(ramdisk_size)
    if dtb_size == 0 or start + dtb_size > len(image):
        raise LayoutError('vendor_boot has no complete DTB section')
    return image[start:start + dtb_size]


def add_arguments(parser):
    """--contained-sink / --legacy-sink for a builder that takes a finished DTB.

    Neither flag means the default, contained; either one states the layout
    the DTB must carry.  The choice lands in args.sink_layout (None, or the
    layout named)."""
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--contained-sink', dest='sink_layout', action='store_const',
                       const=CONTAINED,
                       help='The DTB must carry the contained ABL overlay sink (the default)')
    group.add_argument('--legacy-sink', dest='sink_layout', action='store_const',
                       const=LEGACY,
                       help='The DTB carries the legacy root-level sink on purpose '
                            '(fallback and comparison only); refused otherwise')
    parser.set_defaults(sink_layout=None)
    return group


def check_choice(layout, wanted=None, allow_none=False):
    """Refuse a layout the caller did not ask for; returns the layout.

    wanted is None for the default or the layout an explicit flag named."""
    if wanted is not None and layout != wanted:
        raise LayoutError(f'--{wanted}-sink given, but the DTB carries the {layout} layout')
    if layout == LEGACY and wanted != LEGACY:
        raise LayoutError('the DTB carries the legacy root-level sink, which holds back '
                          'sync_state() of rpmhpd, the NoCs and the PSCI power domains and '
                          'is kept for fallback and comparison only; pass --legacy-sink to '
                          'build with it on purpose')
    if layout == NONE and not allow_none:
        raise LayoutError('the DTB has no ABL overlay sink; ABL will not boot it next to '
                          'the stock dtbo (build it with tools/build-erhai-abl-symbols.py)')
    return layout
