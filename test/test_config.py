import os
import unittest
from functools import partial

import fb_config


class Test(unittest.TestCase):
    def test_config(self):
        test_defaults_path, test_name = _make_test_filename('_test_config')

        self.assertRaises(FileNotFoundError, partial(_make_test_class, test_name))

        test_cfg = {'value_1': 1337}
        fb_config.dump_json(test_defaults_path, test_cfg)

        test_cfg_obj = _make_test_class(test_name)
        result = getattr(test_cfg_obj, 'value_1')
        self.assertEqual(test_cfg['value_1'], result)
        self.assertEqual(test_cfg['value_1'], test_cfg_obj.value_1)

        if os.path.isfile(test_cfg_obj._user_data_path):
            os.unlink(test_cfg_obj._user_data_path)

        test_cfg_obj.value_1 = 42
        self.assertTrue(os.path.isfile(test_cfg_obj._user_data_path))
        result = getattr(test_cfg_obj, 'value_1')
        self.assertEqual(result, 42)

        test_cfg_obj.value_1 = 23
        test_data = fb_config.load_json(test_cfg_obj._user_data_path)
        self.assertEqual(test_data['value_1'], test_cfg_obj.value_1)

        test_cfg_obj.value_1 = 1337
        self.assertFalse(os.path.isfile(test_cfg_obj._user_data_path))

        if os.path.isfile(test_cfg_obj._user_data_path):
            os.unlink(test_cfg_obj._user_data_path)
            self.assertFalse(os.path.isfile(test_cfg_obj._user_data_path))

        os.unlink(test_defaults_path)
        self.assertFalse(os.path.isfile(test_defaults_path))

    def test_updates(self):
        test_defaults_path, test_name = _make_test_filename('_test_updates')
        test_cfg = {'x': 5, 'boobles': False, 'drama': 'MEEP!'}
        fb_config.dump_json(test_defaults_path, test_cfg)

        test_cfg_obj1 = _make_test_class(test_name)
        test_cfg_obj2 = _make_test_class(test_name)

        self.assertEqual(test_cfg_obj1.x, test_cfg_obj2.x)

        if os.path.isfile(test_cfg_obj1._user_data_path):
            os.unlink(test_cfg_obj1._user_data_path)

        new_value = 4223
        test_cfg_obj1.x = new_value
        self.assertEqual(new_value, test_cfg_obj2.x)

        if os.path.isfile(test_cfg_obj1._user_data_path):
            os.unlink(test_cfg_obj1._user_data_path)
        os.unlink(test_defaults_path)


def _make_test_class(name: str) -> fb_config._Settings:
    class _TestClass(fb_config._Settings):
        def __init__(self):
            super().__init__(name)

    return _TestClass()


def _make_test_filename(name: str) -> tuple[str, str]:
    for i in range(1000):
        test_name = f'{name}{i}'
        test_file = f'{test_name}{fb_config._EXT}'
        path = os.path.join(fb_config._DEFAULTS_DIR, test_file)
        if not os.path.isfile(path):
            return path, test_name

    raise RuntimeError(
        f'Could not make file name for "{name}" in {fb_config._DEFAULTS_DIR}'
    )


if __name__ == '__main__':
    unittest.main()
