#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Rebuild the erhai packaging DTB so ABL accepts it next to the stock dtbo.

This unit's ABL refuses a header v2 boot image carrying the plain mainline
sm8750-erhai.dtb: ABL applies the stock dtbo.img overlays onto the boot DTB
and aborts when a dtbo __fixups__ symbol is missing from the boot DTB
__symbols__ (a mainline DTB has none), and it validates the root identity
(qcom,msm-id / qcom,board-id) against the stock tables. This tool rebuilds
the packaging DTB offline, without touching the kernel DTS:

* extract base trees directly from vendor_boot.img and the dtbo.img entries,
  then map every
  symbol named by any stock base __symbols__ or any dtbo entry __fixups__ to
  an inert sink node carrying an explicit linux,phandle, so libufdt fragment
  merges land harmlessly in the sink;
* copy the root identity statements of the stock base table this unit
  actually boots verbatim into the mainline root.

Two sink layouts exist; the manifest records which one was built as
abl_sink_layout, and the boot image builders read it back from the DTB.

contained (the default) puts the sink at /erhai-abl/overlay-sink, in a
container node with status = "disabled" and no compatible, which no symbol
names, so no fragment can reach it.  Inside the container the sink never
becomes a device, its subtree is never parsed for suppliers, and
interconnect provider counting skips it, so rpmhpd, the NoCs, GCC and the
PSCI power domains reach sync_state().  This is the layout daily
deliveries use.

legacy (--legacy-sink) puts the sink at the root as /erhai-abl-overlay-sink,
with every symbol naming it and no container: the layout the installed
releases before 0.1.56 boot with, kept only as a fallback and for comparison
images.  Its known cost: the merged sink ends up with a compatible, status = "ok" and the
phandle cells of every stock provider it stands in for, so it is populated
as a platform device that never binds, and fw_devlink parses its subtree.
The sink has none of the #clock-cells, #interconnect-cells or #reset-cells
the stock lists expect, so their argument cells are read as phandles and
happen to name mainline suppliers (rpmhpd, NoCs, GCC, the PSCI power
domains), whose sync_state() then waits for that consumer forever.

The rebuilt DTB is decompiled again and verified: __symbols__ count and sink
phandle, the sink layout (no container for legacy, the container status for
contained, and no trace of the other layout), byte-faithful root identity,
and full __fixups__ coverage for every dtbo entry. Input and output identity
goes into manifest.json.
"""
import argparse
import hashlib
import json
import re
import struct
import subprocess
import tempfile
from pathlib import Path
import os

from lib.abl_layout import CONTAINED, LEGACY, USE as LAYOUT_USE, LayoutError, vendor_boot_dtb

REPO = Path(__file__).resolve().parent.parent
# Workspace layout: when this repo is checked out at <workspace>/public/<name>,
# shared inputs and build outputs live in the workspace root; standalone
# checkouts keep everything inside the repo. ERHAI_WORKSPACE overrides both.
if (REPO.parent.parent / 'AGENTS.md').is_file() and (REPO.parent.parent / 'kernel/linux').is_dir():
    WS = Path(os.environ.get('ERHAI_WORKSPACE', REPO.parent.parent)).resolve()
else:
    WS = Path(os.environ.get('ERHAI_WORKSPACE', str(REPO))).resolve()
DTC = WS / 'out/kernel-firstboot/scripts/dtc/dtc'
MAINLINE_DTB = WS / 'out/kernel-firstboot/arch/arm64/boot/dts/qcom/sm8750-erhai.dtb'
DTBO_IMG = WS / 'cache/stock-c34/images/dtbo.img'
VENDOR_BOOT = WS / 'cache/stock-c34/images/vendor_boot.img'
DEFAULT_OUT = WS / 'out/abl-dtb'
CONTAINER_NAME = 'erhai-abl'
SINK_NAME = 'overlay-sink'
SINK_PATH = f'/{CONTAINER_NAME}/{SINK_NAME}'
# The root-level sink of the legacy layout (--legacy-sink).
LEGACY_SINK_NAME = 'erhai-abl-overlay-sink'
LEGACY_SINK_PATH = f'/{LEGACY_SINK_NAME}'
SINK_PHANDLE = 0x40000000
IDENTITY_PROPS = ('qcom,msm-id', 'qcom,board-id')
DT_TABLE_MAGIC = 0xd7b7ab1e
FDT_MAGIC = 0xd00dfeed
PROP_RE = re.compile(r'(\S+)\s+=\s+(.*);$')
PHANDLE_RE = re.compile(r'^\s*(?:linux,)?phandle\s*=\s*<(0x[0-9a-fA-F]+|\d+)>\s*;', re.M)


def die(message):
    raise SystemExit(f'error: {message}')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decompile(dtc, dtb):
    return subprocess.run([str(dtc), '-I', 'dtb', '-O', 'dts', str(dtb)],
                          capture_output=True, check=True, text=True).stdout


def compile_dts(dtc, dts, dtb):
    proc = subprocess.run([str(dtc), '-I', 'dts', '-O', 'dtb', '-o', str(dtb), str(dts)],
                          capture_output=True, text=True)
    if proc.returncode:
        die(f'dtc failed on {dts}:\n{proc.stderr}')
    return len(proc.stderr.splitlines())


def opening_re(node):
    # dtc prints every symbol that names a node path as a label prefix when
    # decompiling, so the sink node line can carry thousands of labels.
    return re.compile(r'(?:\w+:\s+)*' + re.escape(node) + r'\s*\{$')


def child_node_properties(text, node):
    """Direct properties of NODE as {name: value_text}.

    NODE is a root child name or a path of node names ("a/b"). Line-based
    brace state machine: node openings end their line with '{', closings
    start with '}'. Value text is kept verbatim (strings, cell arrays and
    string lists alike); only the trailing semicolon is dropped.
    """
    names = node.strip('/').split('/')
    openings = [opening_re(name) for name in names]
    depth = 0
    matched = 0  # how many leading path components are open right now
    target = len(names) + 1
    props = {}
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.endswith('{'):
            depth += 1
            if matched == depth - 2 and matched < len(names) and \
                    openings[matched].match(stripped):
                matched += 1
        elif stripped.startswith('}'):
            if matched == len(names) and depth == target:
                return props
            if matched and matched == depth - 1:
                matched -= 1
            depth -= 1
        elif matched == len(names) and depth == target:
            match = PROP_RE.match(stripped)
            if match:
                props[match.group(1)] = match.group(2)
    if matched < len(names):
        die(f'node "{node}" not found in decompiled text')
    die(f'node "{node}" is not closed in decompiled text')


def root_properties(text):
    """Direct properties of the root node as {name: full statement}."""
    depth = 0
    props = {}
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.endswith('{'):
            depth += 1
        elif stripped.startswith('}'):
            depth -= 1
        elif depth == 1:
            match = PROP_RE.match(stripped)
            if match:
                props[match.group(1)] = stripped
    return props


def extract_base_trees(image_path, out_dir):
    """Decode the original concatenated FDT section, with no old output input."""
    try:
        data = vendor_boot_dtb(image_path.read_bytes())
    except (LayoutError, struct.error) as error:
        die(f'{image_path}: {error}')
    out_dir.mkdir(parents=True, exist_ok=True)
    offset = 0
    paths = []
    while offset < len(data):
        if len(data) - offset < 40:
            die(f'{image_path}: truncated base DTB header at {offset}')
        magic, size = struct.unpack_from('>II', data, offset)
        if magic != FDT_MAGIC or size < 40 or offset + size > len(data):
            die(f'{image_path}: invalid base DTB at {offset}')
        path = out_dir / f'base-{len(paths):02d}.dtb'
        path.write_bytes(data[offset:offset + size])
        paths.append(path)
        offset += size
    return paths


def extract_dtbo_entries(img_path, out_dir):
    data = img_path.read_bytes()
    magic, total, header, entry_size, count, entries_offset, _, _ = \
        struct.unpack('>8I', data[:32])
    if magic != DT_TABLE_MAGIC:
        die(f'{img_path}: bad DT table magic {magic:#010x}')
    if total > len(data):
        die(f'{img_path}: header total_size {total} exceeds file size {len(data)}')
    data = data[:total]  # the flashed image is padded beyond the table size
    if header != 32 or entry_size != 32:
        die(f'{img_path}: unsupported header_size/entry_size {header}/{entry_size}')
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for index in range(count):
        fields = struct.unpack('>8I', data[entries_offset + index * 32:
                                           entries_offset + (index + 1) * 32])
        size, offset, entry_id, rev, custom = fields[0], fields[1], fields[2], fields[3], fields[4:]
        blob = data[offset:offset + size]
        if len(blob) != size or struct.unpack('>I', blob[:4])[0] != FDT_MAGIC:
            die(f'{img_path}: entry {index} is not a valid FDT')
        path = out_dir / f'entry.{index:02d}.dtb'
        reused = path.is_file() and path.read_bytes() == blob
        if not reused:
            path.write_bytes(blob)
        entries.append({'index': index, 'offset': offset, 'size': size,
                        'id': entry_id, 'rev': rev, 'custom': list(custom),
                        'path': str(path), 'reused': reused,
                        'sha256': hashlib.sha256(blob).hexdigest()})
    return entries


def symbol_union(dtc, base_dir, entries):
    by_base = {}
    for dtb in sorted(base_dir.glob('base-*.dtb')):
        by_base[dtb.name] = set(child_node_properties(decompile(dtc, dtb), '__symbols__'))
    if not by_base:
        die(f'no base-*.dtb under {base_dir}')
    by_entry = {}
    for entry in entries:
        name = f"entry.{entry['index']:02d}"
        by_entry[name] = set(child_node_properties(decompile(dtc, entry['path']), '__fixups__'))
    union = sorted(set().union(*by_base.values(), *by_entry.values()))
    return by_base, by_entry, union


def sink_path(legacy=False):
    return LEGACY_SINK_PATH if legacy else SINK_PATH


def check_mainline(text, legacy=False):
    present = [name for name in IDENTITY_PROPS if name in root_properties(text)]
    if present:
        die(f'mainline root already defines {present}; refusing to override real data')
    for node in ('__symbols__', LEGACY_SINK_NAME if legacy else CONTAINER_NAME):
        if any(opening_re(node).match(line.strip()) for line in text.splitlines()):
            die(f'mainline DTB already has a {node} node')
    phandles = {int(match.group(1), 0) for match in PHANDLE_RE.finditer(text)}
    if SINK_PHANDLE in phandles:
        die(f'sink phandle {SINK_PHANDLE:#x} is already used by the mainline DTB')


def inject(text, union, identity, legacy=False):
    props = ['\t' + identity[name] for name in IDENTITY_PROPS if name in identity]
    if legacy:
        subnodes = [f'\t{LEGACY_SINK_NAME} {{',
                    f'\t\tlinux,phandle = <{SINK_PHANDLE:#x}>;',
                    '\t};']
    else:
        subnodes = [f'\t{CONTAINER_NAME} {{',
                    '\t\tstatus = "disabled";',
                    f'\t\t{SINK_NAME} {{',
                    f'\t\t\tlinux,phandle = <{SINK_PHANDLE:#x}>;',
                    '\t\t};',
                    '\t};']
    subnodes += ['\t__symbols__ {']
    subnodes += [f'\t\t{name} = "{sink_path(legacy)}";' for name in union]
    subnodes += ['\t};']
    lines = text.splitlines()
    depth = 0
    start = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.endswith('{'):
            depth += 1
            if start is None:
                if stripped != '/ {':
                    die(f'unexpected line before the root node: {stripped!r}')
                start = index
        elif stripped.startswith('}'):
            depth -= 1
            if depth == 0:
                # dtc requires node properties before subnodes: identity props
                # go first, the sink and __symbols__ nodes close the root.
                return '\n'.join(lines[:start + 1] + props + lines[start + 1:index]
                                 + subnodes + lines[index:]) + '\n'
    die('root node is not closed in the mainline decompile')


def check_layout(text, legacy=False):
    """The sink where the chosen layout puts it, and nothing of the other layout.

    Returns the container description for the report.
    """
    path = sink_path(legacy)
    symbols = child_node_properties(text, '__symbols__')
    wrong = [name for name, value in symbols.items() if value != f'"{path}"']
    if wrong:
        die(f'{len(wrong)} __symbols__ entries do not point to {path}')
    sink = child_node_properties(text, path)
    if sink.get('linux,phandle') != f'<{SINK_PHANDLE:#x}>':
        die(f'sink linux,phandle is {sink.get("linux,phandle")}, want {SINK_PHANDLE:#x}')
    other = CONTAINER_NAME if legacy else LEGACY_SINK_NAME
    if any(opening_re(other).match(line.strip()) for line in text.splitlines()):
        die(f'the {"legacy" if legacy else "contained"} layout must not have a {other} node')
    if legacy:
        return 'none (legacy root-level sink)'
    container = child_node_properties(text, CONTAINER_NAME)
    if container != {'status': '"disabled"'}:
        die(f'{CONTAINER_NAME} must carry only status = "disabled", has {container}')
    return f'/{CONTAINER_NAME} status "disabled", no compatible'


def verify(dtc, final_dtb, union, identity, fixups_by_entry, legacy=False):
    text = decompile(dtc, final_dtb)
    symbols = child_node_properties(text, '__symbols__')
    if set(symbols) != set(union):
        die(f'final __symbols__ has {len(symbols)} entries, union has {len(union)}')
    container = check_layout(text, legacy)
    root = root_properties(text)
    for name, statement in identity.items():
        if root.get(name) != statement:
            die(f'root identity {name!r}: got {root.get(name)!r}, want {statement!r}')
    covered = 0
    for name, fixups in sorted(fixups_by_entry.items()):
        missing = sorted(fixups - set(symbols))
        if missing:
            die(f'{name}: {len(missing)} __fixups__ symbols absent from the final DTB, '
                f'first: {missing[0]}')
        covered += 1
    layout = 'legacy-root' if legacy else 'container=disabled'
    print(f'verification: __symbols__={len(symbols)} sink=ok {layout} identity=ok '
          f'fixups coverage {covered}/{len(fixups_by_entry)} dtbo entries')
    return {'symbols_count': len(symbols),
            'sink_phandle': f'{SINK_PHANDLE:#x}',
            'sink_layout': 'legacy-root' if legacy else 'contained',
            'container': container,
            'root_identity': {name: root[name] for name in identity},
            'fixups_coverage': f'{covered}/{len(fixups_by_entry)} dtbo entries fully covered'}


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUT,
                        help='New output directory (existing DTB with --verify-only)')
    parser.add_argument('--mainline-dtb', type=Path, default=MAINLINE_DTB)
    parser.add_argument('--dtbo-img', type=Path, default=DTBO_IMG)
    stock = parser.add_mutually_exclusive_group()
    stock.add_argument('--vendor-boot', type=Path,
                       help='Original stock image (default: cache/stock-c34/images/vendor_boot.img)')
    stock.add_argument('--base-dir', type=Path,
                       help='Explicit original base-*.dtb inputs instead of a vendor_boot image')
    parser.add_argument('--identity-base', type=Path,
                        help='Explicit stock identity tree (default: selected base index)')
    parser.add_argument('--identity-index', type=int, default=6,
                        help='Base-tree index supplying identity; 6 matches the pinned C.34 input')
    parser.add_argument('--dtbo-dir', type=Path,
                        help='Decoded overlay cache (default: OUTPUT/stock-dtbo)')
    parser.add_argument('--dtc', type=Path, default=DTC)
    parser.add_argument('--verify-only', action='store_true',
                        help='Only re-verify OUTPUT/erhai-abl.dtb against the inputs')
    layout = parser.add_mutually_exclusive_group()
    layout.add_argument('--contained-sink', dest='sink_layout', action='store_const',
                        const=CONTAINED,
                        help='Put the sink in the disabled container /erhai-abl; '
                             'this is the default')
    layout.add_argument('--legacy-sink', dest='sink_layout', action='store_const',
                        const=LEGACY,
                        help='Put the sink at the root (/erhai-abl-overlay-sink) as the '
                             'releases before 0.1.56 did: fallback and comparison only')
    parser.set_defaults(sink_layout=CONTAINED)
    return parser


def build(parser, args, temporary):
    legacy = args.sink_layout == LEGACY
    dtc = args.dtc.resolve()
    vendor_boot = None if args.base_dir else (args.vendor_boot or VENDOR_BOOT).resolve()
    for path in (dtc, args.mainline_dtb, args.dtbo_img, *([vendor_boot] if vendor_boot else [])):
        if not path.is_file():
            parser.error(f'Missing input: {path}')
    if args.identity_index < 0:
        parser.error('--identity-index must be nonnegative')
    base_dir = args.base_dir.resolve() if args.base_dir else temporary / 'stock-base'
    if vendor_boot:
        extract_base_trees(vendor_boot, base_dir)
    identity_base = (args.identity_base or base_dir / f'base-{args.identity_index:02d}.dtb').resolve()
    if not identity_base.is_file():
        parser.error(f'Missing identity tree: {identity_base}')
    identity_source = (f'{vendor_boot}:dtb[{args.identity_index}]'
                       if vendor_boot and not args.identity_base else str(identity_base))
    out = args.output.resolve()
    final_dtb = out / 'erhai-abl.dtb'
    if args.verify_only:
        if not final_dtb.is_file():
            parser.error(f'Missing DTB to verify: {final_dtb}')
    else:
        out.mkdir(parents=True, exist_ok=False)

    entries = extract_dtbo_entries(args.dtbo_img.resolve(),
                                   (args.dtbo_dir or out / 'stock-dtbo').resolve())
    by_base, by_entry, union = symbol_union(dtc, base_dir, entries)
    base_root = root_properties(decompile(dtc, identity_base))
    identity = {name: base_root[name] for name in IDENTITY_PROPS if name in base_root}
    skipped = [name for name in IDENTITY_PROPS if name not in base_root]
    if skipped:
        print(f'note: {identity_base.name} root has no {", ".join(skipped)}; skipped')

    if not args.verify_only:
        text = decompile(dtc, args.mainline_dtb.resolve())
        check_mainline(text, legacy)
        dts = out / 'erhai-abl.dts'
        dts.write_text(inject(text, union, identity, legacy))
        warnings = compile_dts(dtc, dts, final_dtb)
        union_text = '\n'.join(union) + '\n'
        (out / 'symbols-union.txt').write_text(union_text)
        print(f'compiled {final_dtb.name} ({warnings} dtc warning lines)')

    report = verify(dtc, final_dtb, union, identity, by_entry, legacy)
    if not args.verify_only:
        manifest = {
            'status': 'OFFLINE_CANDIDATE_NOT_DEVICE_TESTED',
            'purpose': 'packaging DTB that survives ABL stock-dtbo overlay application '
                       'and root identity checks',
            'abl_sink_layout': args.sink_layout,
            'abl_sink_use': LAYOUT_USE[args.sink_layout],
            'inputs_sha256': ({'vendor_boot.img': sha(vendor_boot)} if vendor_boot else {}) | {
                              'dtbo.img': sha(args.dtbo_img.resolve()),
                              'mainline_dtb': sha(args.mainline_dtb.resolve()),
                              'identity_base': sha(identity_base),
                              'base_dtbs': {name: sha(base_dir / name) for name in sorted(by_base)},
                              'dtc': sha(dtc)},
            'dtbo_entries': entries,
            'symbols': {'base_union': len(set().union(*by_base.values())),
                        'dtbo_fixups_union': len(set().union(*by_entry.values())),
                        'union': len(union),
                        'union_file': 'symbols-union.txt',
                        'union_file_sha256': hashlib.sha256(union_text.encode()).hexdigest()},
            'root_identity': {'source': identity_source,
                              'copied': identity, 'absent_in_source_skipped': skipped},
            'sink': ({'layout': 'legacy-root', 'name': LEGACY_SINK_NAME,
                      'path': LEGACY_SINK_PATH, 'container': None}
                     if legacy else
                     {'layout': 'contained', 'name': SINK_NAME, 'path': SINK_PATH,
                      'container': f'/{CONTAINER_NAME}'})
                    | {'linux,phandle': f'{SINK_PHANDLE:#x}'},
            'outputs_sha256': {'erhai-abl.dts': sha(out / 'erhai-abl.dts'),
                               'erhai-abl.dtb': sha(final_dtb)},
            'verification': report,
        }
        (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'status': 'OK', 'dtb': str(final_dtb), 'dtb_sha256': sha(final_dtb),
                      'abl_sink_layout': args.sink_layout,
                      'sink_layout': report['sink_layout'],
                      'symbols_union': len(union),
                      'fixups_coverage': report['fixups_coverage']}, indent=2))


def main():
    parser = build_parser()
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='erhai-stock-trees-') as directory:
        build(parser, args, Path(directory))


if __name__ == '__main__':
    main()
