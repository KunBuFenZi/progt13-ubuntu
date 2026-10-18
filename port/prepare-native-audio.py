#!/usr/bin/env python3
"""Convert native Music register sections into standard single-bin ACF entries.

Every register/value pair remains byte-identical. The original ACF is preserved;
non-register algorithm metadata is not included in the codec-only output.
"""
import hashlib
import json
from pathlib import Path
import struct

root = Path(__file__).resolve().parent.parent
original = root/'diagnostics/firmware/aw882xx_acf.bin'
data = original.read_bytes()
assert hashlib.sha256(data).hexdigest() == 'd8904ab38a7913626ff7e5ee4ece3230176d0a9e95bb1bd320d5a2c539f7f36d'
proof = json.loads((root/'diagnostics/audio-native-config.json').read_text())
assert set(proof['native_chip_ids'].values()) == {0x2418}

def crc8(payload):
    crc = 0
    for byte in payload:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0x8c if crc & 1 else 0)
    return crc

def parse_bin(blob):
    assert len(blob) >= 60
    fields = struct.unpack_from('<15I',blob)
    checksum, version, kind, data_version, size = fields[:5]
    assert version == 0x01000000 and data_version == 1 and len(blob) == 60+size
    assert checksum == sum(blob[4:]) & 0xffffffff
    assert blob[24:32].rstrip(b'\0') == b'AW88480'
    if kind == 0x2000:
        count = struct.unpack_from('<I',blob,60)[0]
        assert count < 10 and size >= 4+8*count
        result = []
        expected = 4+8*count
        for i in range(count):
            offset,length = struct.unpack_from('<II',blob,64+8*i)
            assert offset == expected and 60+offset+length <= len(blob)
            result += parse_bin(blob[60+offset:60+offset+length])
            expected += length
        assert expected == size
        return result
    if kind == 0:
        assert fields[8:10] == (2,2)
        count = struct.unpack_from('<I',blob,60)[0]
        assert size == 4+count*4
        registers = list(struct.iter_unpack('<HH',blob[64:]))
        assert len({r for r,v in registers}) == count
        assert all(3 <= r <= 0x89 for r,v in registers)
        # Native Music does not contain reset or efuse/programming registers.
        assert not any(0x76 <= r <= 0x7f for r,v in registers)
        return [(blob,registers)]
    assert kind == 0x12, ('Unexpected non-register section',hex(kind))
    return []

parts = {}
for section in proof['sections']:
    if section['profile'] != 0:
        continue
    start,size = section['offset'],section['size']
    payload = data[start:start+size]
    assert crc8(payload) == section['crc8']
    registers = parse_bin(payload)
    assert len(registers) == 1
    parts[section['channel']] = registers[0]
assert set(parts) == {0,1,2,3}
header = bytearray(data[:80])
struct.pack_into('<III',header,52,len(parts)*64,len(parts),80)
table = bytearray()
payloads = bytearray()
details = {}
for channel,(blob,registers) in sorted(parts.items()):
    values = dict(registers)
    assert values[7] == 0xb000+0x111*channel
    assert values[9] == 0xff and values[4] == 0xd040
    table += struct.pack('<I16s4H9I',2,b'aw88480',channel,0xffff,0xffff,0,
                         4,len(blob),80+4*64+len(payloads),crc8(blob),0,0,0,0,0)
    payloads += blob
    details[channel] = {'register_count':len(registers),
                        'register_bytes_sha256':hashlib.sha256(blob[64:]).hexdigest(),
                        'tdm_slot_register':values[7],
                        'native_attenuation':values[5] & 0x3ff}
out = root/'out/audio-native'
out.mkdir(exist_ok=True)
converted = bytes(header+table+payloads)
(out/'aw88480-native-music.acf').write_bytes(converted)
manifest = {'status':'NATIVE_REGISTER_SECTIONS_PREPARED_NOT_CODEC_TESTED',
            'source_sha256':hashlib.sha256(data).hexdigest(),
            'output_sha256':hashlib.sha256(converted).hexdigest(),
            'channels':details,
            'format':'ACF v1 with HDR_REG sections; full native register-bin checksums retained',
            'scope':'No calibration or efuse writes; hardware playback not tested'}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest,indent=2))
