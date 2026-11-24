"""A7 (G3) GPU firmware step and the A7 boards' recipes. Synthetic bytes only."""
import hashlib
import json
from pathlib import Path
import unittest

from orchard import recipe
from orchard.apple import agx
from test_agx_g4p import ldr

ROOT = Path(__file__).resolve().parents[1]
A7_BOARDS = ('j71', 'j72', 'j73', 'j85', 'j85m', 'j86', 'j86m', 'j87', 'j87m', 'n51', 'n53')
LDR = 'lib/firmware/apple/gfx-s5l8960x.bin'
STEP = 'agx-g3-ldr-from-kernelcache@1'


def sha(data):
    return hashlib.sha256(data).hexdigest()


class G3Step(unittest.TestCase):
    def test_the_pinned_ldr_is_returned_byte_for_byte(self):
        one, two = ldr(b'g3 firmware'), ldr(b'another g3 firmware')
        blob = b'\xff' * 5 + one + b'\x00' * 3 + two
        self.assertEqual(agx.extract_g3_ldr(blob, sha(two)), two)
        with self.assertRaisesRegex(ValueError, 'Pinned G3 firmware not found'):
            agx.extract_g3_ldr(blob, '0' * 64)
        with self.assertRaisesRegex(ValueError, '2 G3 firmware candidates'):
            agx.extract_g3_ldr(blob, None)

    def test_the_step_runs_through_a_recipe(self):
        image = ldr(b'g3 firmware')
        blob = b'kernel' + image + b'tail'
        document = {
            'schema': 2, 'device': 'iPad4,4',
            'ipsw': {'version': '12.5.8', 'build': '16H88', 'bytes': 1, 'sha256': '0' * 64,
                     'url': 'https://updates.cdn-apple.com/x.ipsw'},
            'inputs': {'kc': {'ipsw': {'kernelcache': True}, 'sha256': sha(blob)}},
            'outputs': [{'destination': LDR, 'sha256': sha(image),
                         'steps': [{'step': STEP, 'input': 'kc'}]}],
        }
        self.assertEqual(recipe.run(recipe.check(document), lambda name: blob), {LDR: image})


class A7Recipes(unittest.TestCase):
    def test_every_a7_board_installs_the_same_gpu_firmware(self):
        pins = set()
        for board in A7_BOARDS:
            with self.subTest(board=board):
                document = recipe.check(json.loads((ROOT / f'devices/{board}/firmware.json').read_text()))
                output = {o['destination']: o for o in document['outputs']}[LDR]
                name = output['steps'][0]['input']
                self.assertEqual(output['steps'], [{'step': STEP, 'input': name}])
                source = document['inputs'][name]
                self.assertEqual(source['ipsw']['kernelcache'], 'j85ap')
                self.assertEqual(source['ipsw']['restore']['build'], '16H88')
                pins.add((output['sha256'], source['sha256'], source['ipsw']['restore']['url']))
        self.assertEqual(len(pins), 1, 'every A7 board pins the same image')


if __name__ == '__main__':
    unittest.main()
