import unittest
from unittest import mock
import sys
import types
import pathlib

class TestAutoComCLI(unittest.TestCase):
    def setUp(self):
        # patch logger, dirs, AutoComLogger, CommonUtils, execute_with_loop, execute_with_folder
        patcher_logger = mock.patch('components.Logger.AutoComLogger.get_instance')
        patcher_dirs = mock.patch('utils.dirs.get_dirs')
        patcher_common = mock.patch('utils.common.CommonUtils.init_log_file_path')
        patcher_exec_loop = mock.patch('AutoCom.execute_with_loop')
        patcher_exec_folder = mock.patch('AutoCom.execute_with_folder')
        self.mock_logger = patcher_logger.start()
        self.mock_dirs = patcher_dirs.start()
        self.mock_common = patcher_common.start()
        self.mock_exec_loop = patcher_exec_loop.start()
        self.mock_exec_folder = patcher_exec_folder.start()
        self.addCleanup(patcher_logger.stop)
        self.addCleanup(patcher_dirs.stop)
        self.addCleanup(patcher_common.stop)
        self.addCleanup(patcher_exec_loop.stop)
        self.addCleanup(patcher_exec_folder.stop)
        # patch sys.exit
        patcher_exit = mock.patch('sys.exit', side_effect=SystemExit)
        self.mock_exit = patcher_exit.start()
        self.addCleanup(patcher_exit.stop)
        # patch open
        patcher_open = mock.patch('builtins.open', mock.mock_open(read_data='{"a":1}'))
        self.mock_open = patcher_open.start()
        self.addCleanup(patcher_open.stop)
        # patch json.load
        patcher_json = mock.patch('json.load', return_value={"a":1})
        self.mock_json = patcher_json.start()
        self.addCleanup(patcher_json.stop)
        # dirs mock
        self.mock_dirs.return_value.init_project_structure = mock.Mock()
        self.mock_dirs.return_value.get_dict_path = mock.Mock(return_value='dict.json')
        self.mock_dirs.return_value.get_folder_path = mock.Mock(return_value='dicts/')
        self.mock_dirs.return_value.get_config_path = mock.Mock(return_value='config.json')
        # 路径属性用 Path 对象
        self.mock_dirs.return_value.device_logs_dir = pathlib.Path('logs')
        self.mock_dirs.return_value.temp_dir = pathlib.Path('temps')
        self.mock_dirs.return_value.data_store_dir = pathlib.Path('data')
        self.mock_dirs.return_value.session_dir = pathlib.Path('session')

    def run_cli(self, argv):
        # 动态导入cli.py并运行run_main
        sys_argv_backup = sys.argv
        sys.argv = argv
        import importlib
        cli_mod = importlib.import_module('cli')
        importlib.reload(cli_mod)
        try:
            cli_mod.run_main()
        except SystemExit:
            pass
        finally:
            sys.argv = sys_argv_backup

    def test_no_args_prints_welcome(self):
        with self.assertRaises(SystemExit):
            self.run_cli(['cli.py'])
        self.mock_exit.assert_called_with(0)

    def test_init_creates_structure(self):
        with self.assertRaises(SystemExit):
            self.run_cli(['cli.py', '--init'])
        self.mock_dirs.return_value.init_project_structure.assert_called_once()
        self.mock_exit.assert_called_with(0)

    def test_dict_executes_with_loop(self):
        with self.assertRaises(SystemExit):
            self.run_cli(['cli.py', '-d', 'dict.json'])
        self.mock_exec_loop.assert_called_once()

    def test_folder_executes_with_folder(self):
        # patch os.listdir
        with mock.patch('os.listdir', return_value=['1.json', '2.json']):
            with self.assertRaises(SystemExit):
                self.run_cli(['cli.py', '-f', 'dicts/'])
        self.mock_exec_folder.assert_called_once()

    def test_config_file_not_found(self):
        # open抛FileNotFoundError
        self.mock_open.side_effect = FileNotFoundError
        with self.assertRaises(SystemExit):
            self.run_cli(['cli.py', '-d', 'dict.json', '-c', 'notfound.json'])
        self.mock_logger.return_value.log_info.assert_any_call(mock.ANY)
        self.mock_exit.assert_called_with(1)

    def test_config_file_json_error(self):
        # json.load抛JSONDecodeError
        import json
        self.mock_open.side_effect = None
        self.mock_json.side_effect = json.JSONDecodeError('msg', 'doc', 0)
        with self.assertRaises(SystemExit):
            self.run_cli(['cli.py', '-d', 'dict.json', '-c', 'bad.json'])
        self.mock_logger.return_value.log_info.assert_any_call(mock.ANY)
        self.mock_exit.assert_called_with(1)

if __name__ == '__main__':
    unittest.main()
