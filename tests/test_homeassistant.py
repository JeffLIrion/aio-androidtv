import functools
import logging
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, '..')

from aio_adb_shell.exceptions import (
    InvalidChecksumError,
    InvalidCommandError,
    InvalidResponseError,
    TcpTimeoutException,
)
from aio_androidtv import setup
from aio_androidtv.constants import APPS, KEYS, STATE_IDLE, STATE_OFF, STATE_PAUSED, STATE_PLAYING, STATE_STANDBY
from aio_androidtv.exceptions import LockNotAcquiredException

from . import patchers
from .async_wrapper import awaiter


_LOGGER = logging.getLogger(__name__)

SUPPORT_ANDROIDTV = 12345
SUPPORT_FIRETV = 12345

DIRECTION_PULL = "pull"
DIRECTION_PUSH = "push"

class MediaPlayerDevice(object):
    _unique_id = None

    @staticmethod
    def schedule_update_ha_state():
        pass


# =========================================================================== #
#                                                                             #
#                               media_player.py                               #
#                                                                             #
# =========================================================================== #


# Translate from `AndroidTV` / `FireTV` reported state to HA state.
ANDROIDTV_STATES = {
    "off": STATE_OFF,
    "idle": STATE_IDLE,
    "standby": STATE_STANDBY,
    "playing": STATE_PLAYING,
    "paused": STATE_PAUSED,
}


def adb_decorator(override_available=False):
    """Wrap ADB methods and catch exceptions.
    Allows for overriding the available status of the ADB connection via the
    `override_available` parameter.
    """

    def _adb_decorator(func):
        """Wrap the provided ADB method and catch exceptions."""

        @functools.wraps(func)
        async def _adb_exception_catcher(self, *args, **kwargs):
            """Call an ADB-related method and catch exceptions."""
            if not self.available and not override_available:
                return None

            try:
                return await func(self, *args, **kwargs)
            except LockNotAcquiredException:
                # If the ADB lock could not be acquired, skip this command
                return
            except self.exceptions as err:
                _LOGGER.error(
                    "Failed to execute an ADB command. ADB connection re-"
                    "establishing attempt in the next update. Error: %s",
                    err,
                )
                await self.aftv.adb_close()
                self._available = False  # pylint: disable=protected-access
                return None

        return _adb_exception_catcher

    return _adb_decorator


class ADBDevice(MediaPlayerDevice):
    """Representation of an Android TV or Fire TV device."""

    def __init__(
        self, aftv, name, apps, get_sources, turn_on_command, turn_off_command
    ):
        """Initialize the Android TV / Fire TV device."""
        self.aftv = aftv
        self._name = name
        self._app_id_to_name = APPS.copy()
        self._app_id_to_name.update(apps)
        self._app_name_to_id = {
            value: key for key, value in self._app_id_to_name.items()
        }
        self._get_sources = get_sources
        self._keys = KEYS

        self._device_properties = self.aftv.device_properties
        self._unique_id = self._device_properties.get("serialno")

        self.turn_on_command = turn_on_command
        self.turn_off_command = turn_off_command

        # ADB exceptions to catch
        self.exceptions = (
            AttributeError,
            BrokenPipeError,
            TypeError,
            ValueError,
            InvalidChecksumError,
            InvalidCommandError,
            InvalidResponseError,
            TcpTimeoutException,
        )

        # Property attributes
        self._adb_response = None
        self._available = True
        self._current_app = None
        self._sources = None
        self._state = None

    @property
    def app_id(self):
        """Return the current app."""
        return self._current_app

    @property
    def app_name(self):
        """Return the friendly name of the current app."""
        return self._app_id_to_name.get(self._current_app, self._current_app)

    @property
    def available(self):
        """Return whether or not the ADB connection is valid."""
        return self._available

    @property
    def device_state_attributes(self):
        """Provide the last ADB command's response as an attribute."""
        return {"adb_response": self._adb_response}

    @property
    def name(self):
        """Return the device name."""
        return self._name

    @property
    def should_poll(self):
        """Device should be polled."""
        return True

    @property
    def source(self):
        """Return the current app."""
        return self._app_id_to_name.get(self._current_app, self._current_app)

    @property
    def source_list(self):
        """Return a list of running apps."""
        return self._sources

    @property
    def state(self):
        """Return the state of the player."""
        return self._state

    @property
    def unique_id(self):
        """Return the device unique id."""
        return self._unique_id

    @adb_decorator()
    async def media_play(self):
        """Send play command."""
        await self.aftv.media_play()

    @adb_decorator()
    async def media_pause(self):
        """Send pause command."""
        await self.aftv.media_pause()

    @adb_decorator()
    async def media_play_pause(self):
        """Send play/pause command."""
        await self.aftv.media_play_pause()

    @adb_decorator()
    async def turn_on(self):
        """Turn on the device."""
        if self.turn_on_command:
            await self.aftv.adb_shell(self.turn_on_command)
        else:
            await self.aftv.turn_on()

    @adb_decorator()
    async def turn_off(self):
        """Turn off the device."""
        if self.turn_off_command:
            await self.aftv.adb_shell(self.turn_off_command)
        else:
            await self.aftv.turn_off()

    @adb_decorator()
    async def media_previous_track(self):
        """Send previous track command (results in rewind)."""
        await self.aftv.media_previous_track()

    @adb_decorator()
    async def media_next_track(self):
        """Send next track command (results in fast-forward)."""
        await self.aftv.media_next_track()

    @adb_decorator()
    async def select_source(self, source):
        """Select input source.
        If the source starts with a '!', then it will close the app instead of
        opening it.
        """
        if isinstance(source, str):
            if not source.startswith("!"):
                await self.aftv.launch_app(self._app_name_to_id.get(source, source))
            else:
                source_ = source[1:].lstrip()
                await self.aftv.stop_app(self._app_name_to_id.get(source_, source_))

    @adb_decorator()
    async def adb_command(self, cmd):
        """Send an ADB command to an Android TV / Fire TV device."""
        key = self._keys.get(cmd)
        if key:
            await self.aftv.adb_shell("input keyevent {}".format(key))
            self._adb_response = None
            self.schedule_update_ha_state()
            return

        if cmd == "GET_PROPERTIES":
            self._adb_response = str(await self.aftv.get_properties_dict())
            self.schedule_update_ha_state()
            return self._adb_response

        response = await self.aftv.adb_shell(cmd)
        if isinstance(response, str) and response.strip():
            self._adb_response = response.strip()
        else:
            self._adb_response = None

        self.schedule_update_ha_state()
        return self._adb_response

    @adb_decorator()
    async def adb_filesync(self, direction, local_path, device_path):
        """Transfer a file between your HA instance and an Android TV / Fire TV device."""
        if direction == DIRECTION_PULL:
            await self.aftv.adb_pull(local_path, device_path)
        else:
            await self.aftv.adb_push(local_path, device_path)


class AndroidTVDevice(ADBDevice):
    """Representation of an Android TV device."""

    def __init__(
        self, aftv, name, apps, get_sources, turn_on_command, turn_off_command
    ):
        """Initialize the Android TV device."""
        super().__init__(
            aftv, name, apps, get_sources, turn_on_command, turn_off_command
        )

        self._is_volume_muted = None
        self._volume_level = None

    @adb_decorator(override_available=True)
    async def update(self):
        """Update the device state and, if necessary, re-connect."""
        # Check if device is disconnected.
        if not self._available:
            # Try to connect
            self._available = await self.aftv.adb_connect(always_log_errors=False)

        # If the ADB connection is not intact, don't update.
        if not self._available:
            return

        # Get the updated state and attributes.
        (
            state,
            self._current_app,
            running_apps,
            _,
            self._is_volume_muted,
            self._volume_level,
        ) = await self.aftv.update(self._get_sources)

        self._state = ANDROIDTV_STATES.get(state)
        if self._state is None:
            self._available = False

        if running_apps:
            self._sources = [
                self._app_id_to_name.get(app_id, app_id) for app_id in running_apps
            ]
        else:
            self._sources = None

    @property
    def is_volume_muted(self):
        """Boolean if volume is currently muted."""
        return self._is_volume_muted

    @property
    def supported_features(self):
        """Flag media player features that are supported."""
        return SUPPORT_ANDROIDTV

    @property
    def volume_level(self):
        """Return the volume level."""
        return self._volume_level

    @adb_decorator()
    async def media_stop(self):
        """Send stop command."""
        await self.aftv.media_stop()

    @adb_decorator()
    async def mute_volume(self, mute):
        """Mute the volume."""
        await self.aftv.mute_volume()

    @adb_decorator()
    async def volume_down(self):
        """Send volume down command."""
        self._volume_level = await self.aftv.volume_down(self._volume_level)

    @adb_decorator()
    async def volume_up(self):
        """Send volume up command."""
        self._volume_level = await self.aftv.volume_up(self._volume_level)


class FireTVDevice(ADBDevice):
    """Representation of a Fire TV device."""

    @adb_decorator(override_available=True)
    async def update(self):
        """Update the device state and, if necessary, re-connect."""
        # Check if device is disconnected.
        if not self._available:
            # Try to connect
            self._available = await self.aftv.adb_connect(always_log_errors=False)

        # If the ADB connection is not intact, don't update.
        if not self._available:
            return

        # Get the `state`, `current_app`, and `running_apps`.
        state, self._current_app, running_apps = await self.aftv.update(self._get_sources)

        self._state = ANDROIDTV_STATES.get(state)
        if self._state is None:
            self._available = False

        if running_apps:
            self._sources = [
                self._app_id_to_name.get(app_id, app_id) for app_id in running_apps
            ]
        else:
            self._sources = None

    @property
    def supported_features(self):
        """Flag media player features that are supported."""
        return SUPPORT_FIRETV

    @adb_decorator()
    async def media_stop(self):
        """Send stop (back) command."""
        await self.aftv.back()


# =========================================================================== #
#                                                                             #
#                            test_media_player.py                             #
#                                                                             #
# =========================================================================== #


class TestAndroidTVPythonImplementation(unittest.TestCase):
    """Test the androidtv media player for an Android TV device."""

    PATCH_KEY = "python"

    @awaiter
    async def setUp(self):
        """Set up an `AndroidTVDevice` media player."""
        with patchers.PATCH_ADB_DEVICE_TCP, patchers.patch_connect(True)[self.PATCH_KEY], patchers.patch_shell("")[self.PATCH_KEY]:
            aftv = await setup("HOST", 5555, device_class="androidtv")
            self.aftv = AndroidTVDevice(aftv, "Fake Android TV", {}, True, None, None)

    @awaiter
    async def test_reconnect(self):
        """Test that the error and reconnection attempts are logged correctly.

        "Handles device/service unavailable. Log a warning once when
        unavailable, log once when reconnected."

        https://developers.home-assistant.io/docs/en/integration_quality_scale_index.html
        """
        with self.assertLogs(level=logging.WARNING) as logs:
            with patchers.patch_connect(False)[self.PATCH_KEY], patchers.patch_shell(error=True)[self.PATCH_KEY]:
                for _ in range(5):
                    await self.aftv.update()
                    self.assertFalse(self.aftv.available)
                    self.assertIsNone(self.aftv.state)

        assert len(logs.output) == 2
        assert logs.output[0].startswith("ERROR")
        assert logs.output[1].startswith("WARNING")

        with self.assertLogs(level=logging.DEBUG) as logs:
            with patchers.patch_connect(True)[self.PATCH_KEY], patchers.patch_shell("")[self.PATCH_KEY]:
                # Update 1 will reconnect
                await self.aftv.update()
                self.assertTrue(self.aftv.available)

                # Update 2 will update the state
                await self.aftv.update()
                self.assertTrue(self.aftv.available)
                self.assertIsNotNone(self.aftv.state)

        assert (
            "ADB connection to {}:{} successfully established".format(self.aftv.aftv.host, self.aftv.aftv.port)
            in logs.output[0]
        )

    @awaiter
    async def test_adb_shell_returns_none(self):
        """Test the case that the ADB shell command returns `None`.

        The state should be `None` and the device should be unavailable.
        """
        with patchers.patch_shell(None)[self.PATCH_KEY]:
            await self.aftv.update()
            self.assertFalse(self.aftv.available)
            self.assertIsNone(self.aftv.state)

        with patchers.patch_connect(True)[self.PATCH_KEY], patchers.patch_shell("")[self.PATCH_KEY]:
            # Update 1 will reconnect
            await self.aftv.update()
            self.assertTrue(self.aftv.available)

            # Update 2 will update the state
            await self.aftv.update()
            self.assertTrue(self.aftv.available)
            self.assertIsNotNone(self.aftv.state)


class TestFireTVPythonImplementation(TestAndroidTVPythonImplementation):
    """Test the androidtv media player for a Fire TV device."""

    @awaiter
    async def setUp(self):
        """Set up a `FireTVDevice` media player."""
        with patchers.PATCH_ADB_DEVICE_TCP, patchers.patch_connect(True)[self.PATCH_KEY], patchers.patch_shell("")[self.PATCH_KEY]:
            aftv = await setup("HOST", 5555, device_class="firetv")
            self.aftv = FireTVDevice(aftv, "Fake Fire TV", {}, True, None, None)


@unittest.skip
class TestADBCommandAndFileSync(unittest.TestCase):
    """Test ADB and FileSync services."""

    @awaiter
    async def test_adb_command(self):
        """Test sending a command via the `androidtv.adb_command` service."""
        patch_key = "server"
        command = "test command"
        response = "test response"

        with patchers.patch_connect(True)[patch_key], patchers.patch_shell("")[patch_key]:
            aftv = setup(
                "HOST", 5555, adb_server_ip="ADB_SERVER_IP", device_class="androidtv"
            )
            self.aftv = AndroidTVDevice(aftv, "Fake Android TV", {}, True, None, None)

        with patch("aio_androidtv.basetv.BaseTV.adb_shell", return_value=response) as patch_shell:
            await self.aftv.adb_command(command)

            patch_shell.assert_called_with(command)
            assert self.aftv._adb_response == response

    @awaiter
    async def test_adb_command_key(self):
        """Test sending a key command via the `androidtv.adb_command` service."""
        patch_key = "server"
        command = "HOME"
        response = None

        with patchers.patch_connect(True)[patch_key], patchers.patch_shell("")[patch_key]:
            aftv = setup(
                "HOST", 5555, adb_server_ip="ADB_SERVER_IP", device_class="androidtv"
            )
            self.aftv = AndroidTVDevice(aftv, "Fake Android TV", {}, True, None, None)

        with patch("aio_androidtv.basetv.BaseTV.adb_shell", return_value=response) as patch_shell:
            self.aftv.adb_command(command)

            patch_shell.assert_called_with("input keyevent {}".format(self.aftv._keys[command]))
            assert self.aftv._adb_response is None

    @awaiter
    async def test_adb_command_get_properties(self):
        """Test sending the "GET_PROPERTIES" command via the `androidtv.adb_command` service."""
        patch_key = "server"
        command = "GET_PROPERTIES"
        response = {"key": "value"}

        with patchers.patch_connect(True)[patch_key], patchers.patch_shell("")[patch_key]:
            aftv = setup(
                "HOST", 5555, adb_server_ip="ADB_SERVER_IP", device_class="androidtv"
            )
            self.aftv = AndroidTVDevice(aftv, "Fake Android TV", {}, True, None, None)

        with patch("aio_androidtv.androidtv.AndroidTV.get_properties_dict", return_value=response) as patch_get_props:
            self.aftv.adb_command(command)

            assert patch_get_props.called
            assert self.aftv._adb_response == str(response)

    @awaiter
    async def test_update_lock_not_acquired(self):
        """Test that the state does not get updated when a `LockNotAcquiredException` is raised."""
        patch_key = "server"

        with patchers.patch_connect(True)[patch_key], patchers.patch_shell("")[patch_key]:
            aftv = setup(
                "HOST", 5555, adb_server_ip="ADB_SERVER_IP", device_class="androidtv"
            )
            self.aftv = AndroidTVDevice(aftv, "Fake Android TV", {}, True, None, None)

        with patchers.patch_shell("")[patch_key]:
            self.aftv.update()
            assert self.aftv.state == STATE_OFF

        with patch("aio_androidtv.androidtv.AndroidTV.update", side_effect=LockNotAcquiredException):
            with patchers.patch_shell("1")[patch_key]:
                self.aftv.update()
                assert self.aftv.state == STATE_OFF

        with patchers.patch_shell("1")[patch_key]:
            self.aftv.update()
            assert self.aftv.state == STATE_IDLE
