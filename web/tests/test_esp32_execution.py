import io
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from esp32_execution import ESP32Executions
from esp32_worker import probe, main


class BoardTests(unittest.TestCase):
    def test_failed_chip_check_prevents_build_and_flash(self):
        with patch('sys.argv', ['worker', '--port', 'COM3', '--action', 'flash']), patch('esp32_worker.probe', side_effect=RuntimeError('wrong chip')), patch('esp32_worker.subprocess.run') as command:
            with self.assertRaises(RuntimeError): main()
            command.assert_not_called()

    def test_missing_board_never_starts_process(self):
        manager = ESP32Executions(Path.cwd(), {})
        with patch.object(manager, 'settings', return_value={}), patch.object(manager, 'ports', return_value=[]), patch('esp32_execution.subprocess.Popen') as spawn:
            for action in ('flash', 'restart'):
                with self.assertRaisesRegex(ValueError, 'esp32_not_connected'):
                    manager.start('tflite', 'COM3', action)
            spawn.assert_not_called()

    def test_probe_requires_present_port_and_confirms_chip(self):
        with patch('esp32_worker.ports', return_value=[]), patch('esp32_worker.subprocess.run') as command:
            with self.assertRaises(RuntimeError): probe('COM3')
            command.assert_not_called()
        with patch('esp32_worker.ports', return_value=[{'port':'COM3'}]), patch('esp32_worker.subprocess.run') as command:
            probe('COM3')
            args = command.call_args.args[0]
            self.assertIn('chip_id', args)
            self.assertEqual(args[args.index('--chip')+1], 'esp32')

    def test_serial_logs_trigger_import_only_after_http_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = ESP32Executions(tmp, {})
            manager.state = dict(status='running', phase='checking', ip=None, runtime='wasm', reports=[], importStatus='waiting')
            lines = '@@esp32 {"phase":"monitoring"}\nConectado ao Wi-Fi. IP: 192.168.0.18\nServidor HTTP iniciado\nServidor HTTP iniciado\n'
            process = Mock(stdout=io.StringIO(lines), stdin=io.StringIO())
            process.wait.return_value = 0
            with patch('esp32_execution.import_reports', return_value={'files':['report.csv'], 'warnings':[]}) as importer:
                manager._watch(process, True)
                importer.assert_called_once_with(manager.root, '192.168.0.18', 'wasm')
            self.assertEqual(manager.state['reports'], ['report.csv'])
            self.assertEqual(manager.state['status'], 'completed')

    def test_stop_does_not_interrupt_flashing(self):
        manager = ESP32Executions(Path.cwd(), {})
        manager.state = dict(status='running', phase='flashing')
        manager.process = Mock()
        with self.assertRaises(RuntimeError): manager.stop_monitor()
        manager.process.stdin.write.assert_not_called()
        manager.state['phase'] = 'monitoring'
        manager.stop_monitor()
        manager.process.stdin.write.assert_called_once_with('stop\n')
