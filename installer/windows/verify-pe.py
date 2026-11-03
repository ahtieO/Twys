"""Verify the compiled PE has a GUI subsystem and the exact supplied ICO images.

pefile is installed by PyInstaller on Windows. This checks embedded resource bytes,
not just whether Windows can return an arbitrary default executable icon.
"""
from pathlib import Path
import struct


def ico_images(path):
    data = path.read_bytes()
    reserved, kind, count = struct.unpack_from('<HHH', data)
    assert (reserved, kind) == (0, 1) and count, 'Invalid source ICO'
    images = []
    for index in range(count):
        width, height, colors, reserved, planes, depth, size, offset = struct.unpack_from(
            '<BBBBHHII', data, 6 + index * 16)
        image = data[offset:offset + size]
        assert len(image) == size, 'Truncated source ICO'
        images.append((width, height, colors, planes, depth, image))
    return images


def verify(executable, icon):
    import pefile
    with pefile.PE(str(executable)) as pe:
        assert pe.FILE_HEADER.Machine == 0x8664, 'TWYS executable must be x64'
        assert pe.OPTIONAL_HEADER.Subsystem == 2, 'TWYS must use the GUI subsystem'
        resources = {entry.id: entry for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries}
        assert 3 in resources and 14 in resources, 'Embedded icon resources missing'
        images = {}
        for entry in resources[3].directory.entries:
            resource = entry.directory.entries[0].data.struct
            images[entry.id] = pe.get_data(resource.OffsetToData, resource.Size)
        expected = ico_images(icon)
        for group in resources[14].directory.entries:
            resource = group.directory.entries[0].data.struct
            data = pe.get_data(resource.OffsetToData, resource.Size)
            reserved, kind, count = struct.unpack_from('<HHH', data)
            if (reserved, kind, count) != (0, 1, len(expected)):
                continue
            actual = []
            for index in range(count):
                width, height, colors, _, planes, depth, size, image_id = struct.unpack_from(
                    '<BBBBHHIH', data, 6 + index * 14)
                image = images[image_id]
                assert len(image) == size, 'Embedded icon resource truncated'
                actual.append((width, height, colors, planes, depth, image))
            if actual == expected:
                print('TWYS x64 GUI executable contains the exact supplied icon images.')
                return
        raise AssertionError('Executable icon does not match assets/twys-icon.ico')


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[2]
    verify(root / 'dist/TWYS/TWYS.exe', root / 'assets/twys-icon.ico')
