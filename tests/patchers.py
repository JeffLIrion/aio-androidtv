"""Define patches used for androidtv tests."""

from unittest.mock import patch

try:
    from unittest.mock import AsyncMock
except ImportError:
    from unittest.mock import MagicMock

    class AsyncMock(MagicMock):
        async def __call__(self, *args, **kwargs):
            return super(AsyncMock, self).__call__(*args, **kwargs)


KEY_PYTHON = "python"
KEY_SERVER = "server"


class AdbDeviceTcpFake(object):
    """A fake of the `aio_adb_shell.adb_device.AdbDeviceTcp` class."""

    def __init__(self, *args, **kwargs):
        """Initialize a fake `adb_shell.adb_device.AdbDeviceTcp` instance."""
        self.available = False

    async def close(self):
        """Close the socket connection."""
        self.available = False

    async def connect(self, *args, **kwargs):
        """Try to connect to a device."""
        raise NotImplementedError

    async def push(self, *args, **kwargs):
        """Push a file to the device."""

    async def pull(self, *args, **kwargs):
        """Pull a file from the device."""

    async def shell(self, cmd, *args, **kwargs):
        """Send an ADB shell command."""
        return None


class ClientFakeSuccess(object):
    """A fake of the `ppadb.client.Client` class when the connection and shell commands succeed."""

    def __init__(self, host="127.0.0.1", port=5037):
        """Initialize a `ClientFakeSuccess` instance."""
        self._devices = []

    def devices(self):
        """Get a list of the connected devices."""
        return self._devices

    def device(self, serial):
        """Mock the `Client.device` method when the device is connected via ADB."""
        device = DeviceFake(serial)
        self._devices.append(device)
        return device


class ClientFakeFail(object):
    """A fake of the `ppadb.client.Client` class when the connection and shell commands fail."""

    def __init__(self, host="127.0.0.1", port=5037):
        """Initialize a `ClientFakeFail` instance."""
        self._devices = []

    def devices(self):
        """Get a list of the connected devices."""
        return self._devices

    def device(self, serial):
        """Mock the `Client.device` method when the device is not connected via ADB."""
        self._devices = []


class DeviceFake(object):
    """A fake of the `ppadb.device.Device` class."""

    def __init__(self, host):
        """Initialize a `DeviceFake` instance."""
        self.host = host

    def get_serial_no(self):
        """Get the serial number for the device (IP:PORT)."""
        return self.host

    def push(self, *args, **kwargs):
        """Push a file to the device."""

    def pull(self, *args, **kwargs):
        """Pull a file from the device."""

    def shell(self, cmd):
        """Send an ADB shell command."""
        raise NotImplementedError

    def screencap(self):
        """Take a screencap."""
        raise NotImplementedError


def patch_connect(success):
    """Mock the `adb_shell.adb_device.AdbDeviceTcp` and `ppadb.client.Client` classes."""

    async def connect_success_python(self, *args, **kwargs):
        """Mock the `AdbDeviceTcpFake.connect` method when it succeeds."""
        self.available = True

    async def connect_fail_python(self, *args, **kwargs):
        """Mock the `AdbDeviceTcpFake.connect` method when it fails."""
        raise OSError

    if success:
        return {KEY_PYTHON: patch("{}.AdbDeviceTcpFake.connect".format(__name__), connect_success_python), KEY_SERVER: patch("aio_androidtv.adb_manager.Client", ClientFakeSuccess)}
    return {KEY_PYTHON: patch("{}.AdbDeviceTcpFake.connect".format(__name__), connect_fail_python), KEY_SERVER: patch("aio_androidtv.adb_manager.Client", ClientFakeFail)}


def patch_shell(response=None, error=False):
    """Mock the `AdbDeviceTcpFake.shell` and `DeviceFake.shell` methods."""

    async def shell_success(self, cmd, *args, **kwargs):
        """Mock the `AdbDeviceTcpFake.shell` and `DeviceFake.shell` methods when they are successful."""
        self.shell_cmd = cmd
        return response

    def delete_shell_success(self, cmd, *args, **kwargs):
        """Mock the `AdbDeviceTcpFake.shell` and `DeviceFake.shell` methods when they are successful."""
        self.shell_cmd = cmd
        return response

    async def shell_fail_python(self, cmd, *args, **kwargs):
        """Mock the `AdbDeviceTcpFake.shell` method when it fails."""
        self.shell_cmd = cmd
        raise AttributeError

    def shell_fail_server(self, cmd):
        """Mock the `DeviceFake.shell` method when it fails."""
        self.shell_cmd = cmd
        raise ConnectionResetError

    if not error:
        return {KEY_PYTHON: patch("{}.AdbDeviceTcpFake.shell".format(__name__), shell_success), KEY_SERVER: patch("{}.DeviceFake.shell".format(__name__), delete_shell_success)}
    return {KEY_PYTHON: patch("{}.AdbDeviceTcpFake.shell".format(__name__), shell_fail_python), KEY_SERVER: patch("{}.DeviceFake.shell".format(__name__), shell_fail_server)}


PATCH_PUSH = {KEY_PYTHON: patch("{}.AdbDeviceTcpFake.push".format(__name__), new_callable=AsyncMock), KEY_SERVER: patch("{}.DeviceFake.push".format(__name__))}

PATCH_PULL = {KEY_PYTHON: patch("{}.AdbDeviceTcpFake.pull".format(__name__), new_callable=AsyncMock), KEY_SERVER: patch("{}.DeviceFake.pull".format(__name__))}

PATCH_ADB_DEVICE_TCP = patch("aio_androidtv.adb_manager.AdbDeviceTcp", AdbDeviceTcpFake)


class CustomException(Exception):
    """A custom exception type."""


PATCH_CONNECT_FAIL_CUSTOM_EXCEPTION = {KEY_PYTHON: patch("{}.AdbDeviceTcpFake.connect".format(__name__), side_effect=CustomException), KEY_SERVER: patch("{}.ClientFakeSuccess.devices".format(__name__), side_effect=CustomException)}
