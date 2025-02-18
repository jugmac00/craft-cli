#
# Copyright 2021 Canonical Ltd.
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License version 3 as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""Tests that check the whole Emitter machinery."""

import logging
import sys
from unittest.mock import call, patch

import pytest

from craft_cli import messages
from craft_cli.errors import CraftError
from craft_cli.messages import Emitter, EmitterMode, _Handler


@pytest.fixture(autouse=True)
def clean_logging_handler():
    """Remove the used handler to properly isolate tests."""
    logger = logging.getLogger("")
    to_remove = [x for x in logger.handlers if isinstance(x, _Handler)]
    for handler in to_remove:
        logger.removeHandler(handler)


class RecordingEmitter(Emitter):
    """Class to cheat pyright.

    Otherwise it complains I'm setting printer_class to Emitter.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.printer_calls = []


@pytest.fixture
def get_initiated_emitter(tmp_path, monkeypatch):
    """Provide an initiated Emitter ready to test.

    It has a patched "printer" and an easy way to test its calls (after it was initiated).

    It's used almost in all tests (except those that test the init call).
    """
    fake_logpath = str(tmp_path / "fakelog.log")
    monkeypatch.setattr(messages, "_get_log_filepath", lambda appname: fake_logpath)
    with patch("craft_cli.messages._Printer", autospec=True) as mock_printer:

        def func(mode, greeting="default greeting"):
            emitter = RecordingEmitter()
            emitter.init(mode, "testappname", greeting)
            emitter.printer_calls = mock_printer.mock_calls
            emitter.printer_calls.clear()
            return emitter

        yield func


# -- tests for init and setting/getting mode


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.NORMAL,
    ],
)
def test_init_quietish(mode, tmp_path, monkeypatch):
    """Init the class in some quiet-ish mode."""
    # avoid using a real log file
    fake_logpath = str(tmp_path / "fakelog.log")
    monkeypatch.setattr(messages, "_get_log_filepath", lambda appname: fake_logpath)

    greeting = "greeting"
    emitter = Emitter()
    with patch("craft_cli.messages._Printer") as mock_printer:
        emitter.init(mode, "testappname", greeting)

    assert emitter._mode == mode
    assert mock_printer.mock_calls == [
        call(fake_logpath),  # the _Printer instantiation, passing the log filepath
        call().show(None, "greeting"),  # the greeting, only sent to the log
    ]

    # log handler is properly setup
    logger = logging.getLogger("")
    (handler,) = [x for x in logger.handlers if isinstance(x, _Handler)]
    assert handler.mode == mode


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.VERBOSE,
        EmitterMode.TRACE,
    ],
)
def test_init_verboseish(mode, tmp_path, monkeypatch):
    """Init the class in some verbose-ish mode."""
    # avoid using a real log file
    fake_logpath = str(tmp_path / "fakelog.log")
    monkeypatch.setattr(messages, "_get_log_filepath", lambda appname: fake_logpath)

    greeting = "greeting"
    emitter = Emitter()
    with patch("craft_cli.messages._Printer") as mock_printer:
        emitter.init(mode, "testappname", greeting)

    assert emitter._mode == mode
    log_locat = f"Logging execution to {fake_logpath!r}"
    assert mock_printer.mock_calls == [
        call(fake_logpath),  # the _Printer instantiation, passing the log filepath
        call().show(None, "greeting"),  # the greeting, only sent to the log
        call().show(sys.stderr, greeting, use_timestamp=True, end_line=True, avoid_logging=True),
        call().show(sys.stderr, log_locat, use_timestamp=True, end_line=True, avoid_logging=True),
    ]

    # log handler is properly setup
    logger = logging.getLogger("")
    (handler,) = [x for x in logger.handlers if isinstance(x, _Handler)]
    assert handler.mode == mode


@pytest.mark.parametrize("method_name", [x for x in dir(Emitter) if x[0] != "_" and x != "init"])
def test_needs_init(method_name):
    """Check that calling other methods needs emitter first to be initiated."""
    emitter = Emitter()
    method = getattr(emitter, method_name)
    with pytest.raises(RuntimeError, match="Emitter needs to be initiated first"):
        method()


def test_init_receiving_logfile(tmp_path, monkeypatch):
    """Init the class in some verbose-ish mode."""
    # ensure it's not using the standard log filepath provider (that pollutes user dirs)
    monkeypatch.setattr(messages, "_get_log_filepath", None)

    greeting = "greeting"
    emitter = Emitter()
    fake_logpath = tmp_path / "fakelog.log"
    with patch("craft_cli.messages._Printer") as mock_printer:
        emitter.init(EmitterMode.VERBOSE, "testappname", greeting, log_filepath=fake_logpath)

    # filepath is properly informed and passed to the printer
    log_locat = f"Logging execution to {str(fake_logpath)!r}"
    assert mock_printer.mock_calls == [
        call(fake_logpath),  # the _Printer instantiation, passing the log filepath
        call().show(None, "greeting"),  # the greeting, only sent to the log
        call().show(sys.stderr, greeting, use_timestamp=True, end_line=True, avoid_logging=True),
        call().show(sys.stderr, log_locat, use_timestamp=True, end_line=True, avoid_logging=True),
    ]


def test_init_double_regular_mode(tmp_path, monkeypatch):
    """Double init in regular usage mode."""
    # ensure it's not using the standard log filepath provider (that pollutes user dirs)
    monkeypatch.setattr(messages, "_get_log_filepath", lambda appname: tmp_path / "fakelog.log")

    emitter = Emitter()

    with patch("craft_cli.messages._Printer"):
        emitter.init(EmitterMode.VERBOSE, "testappname", "greeting")

        with pytest.raises(RuntimeError, match="Double Emitter init detected!"):
            emitter.init(EmitterMode.VERBOSE, "testappname", "greeting")


def test_init_double_tests_mode(tmp_path, monkeypatch):
    """Double init in tests usage mode."""
    # ensure it's not using the standard log filepath provider (that pollutes user dirs)
    monkeypatch.setattr(messages, "_get_log_filepath", lambda appname: tmp_path / "fakelog.log")

    monkeypatch.setattr(messages, "TESTMODE", True)
    emitter = Emitter()

    with patch("craft_cli.messages._Printer"):
        with patch.object(emitter, "_stop") as mock_stop:
            emitter.init(EmitterMode.VERBOSE, "testappname", "greeting")
            assert mock_stop.called is False
            emitter.init(EmitterMode.VERBOSE, "testappname", "greeting")
            assert mock_stop.called is True


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.NORMAL,
    ],
)
def test_set_mode_quietish(get_initiated_emitter, mode):
    """Set the class to some quiet-ish mode."""
    greeting = "greeting"
    emitter = get_initiated_emitter(EmitterMode.QUIET, greeting=greeting)
    emitter.set_mode(mode)

    assert emitter._mode == mode
    assert emitter.get_mode() == mode
    assert emitter.printer_calls == []

    # log handler is affected
    logger = logging.getLogger("")
    (handler,) = [x for x in logger.handlers if isinstance(x, _Handler)]
    assert handler.mode == mode


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.VERBOSE,
        EmitterMode.TRACE,
    ],
)
def test_set_mode_verboseish(get_initiated_emitter, mode):
    """Set the class to some verbose-ish mode."""
    greeting = "greeting"
    emitter = get_initiated_emitter(EmitterMode.QUIET, greeting=greeting)
    emitter.set_mode(mode)

    assert emitter._mode == mode
    assert emitter.get_mode() == mode
    log_locat = f"Logging execution to {emitter._log_filepath!r}"
    assert emitter.printer_calls == [
        call().show(sys.stderr, greeting, use_timestamp=True, avoid_logging=True, end_line=True),
        call().show(sys.stderr, log_locat, use_timestamp=True, avoid_logging=True, end_line=True),
    ]

    # log handler is affected
    logger = logging.getLogger("")
    (handler,) = [x for x in logger.handlers if isinstance(x, _Handler)]
    assert handler.mode == mode


# -- tests for emitting messages of all kind


@pytest.mark.parametrize("mode", EmitterMode)  # all modes!
def test_message_final(get_initiated_emitter, mode):
    """Emit a final message."""
    emitter = get_initiated_emitter(mode)
    emitter.message("some text")

    assert emitter.printer_calls == [
        call().show(sys.stdout, "some text", use_timestamp=False),
    ]


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.NORMAL,
    ],
)
def test_message_intermediate_quietish(get_initiated_emitter, mode):
    """Emit an intermediate message when in a quiet-ish mode."""
    emitter = get_initiated_emitter(mode)
    emitter.message("some text", intermediate=True)

    assert emitter.printer_calls == [
        call().show(sys.stdout, "some text", use_timestamp=False),
    ]


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.VERBOSE,
        EmitterMode.TRACE,
    ],
)
def test_message_intermediate_verboseish(get_initiated_emitter, mode):
    """Emit an intermediate message when in a verbose-ish mode."""
    emitter = get_initiated_emitter(mode)
    emitter.message("some text", intermediate=True)

    assert emitter.printer_calls == [
        call().show(sys.stdout, "some text", use_timestamp=True),
    ]


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.NORMAL,
        EmitterMode.VERBOSE,
    ],
)
def test_trace_in_non_trace_modes(get_initiated_emitter, mode):
    """Only log the message."""
    emitter = get_initiated_emitter(mode)
    emitter.trace("some text")

    assert emitter.printer_calls == [
        call().show(None, "some text", use_timestamp=True),
    ]


def test_trace_in_trace_mode(get_initiated_emitter):
    """Log the message and show it in stderr."""
    emitter = get_initiated_emitter(EmitterMode.TRACE)
    emitter.trace("some text")

    assert emitter.printer_calls == [
        call().show(sys.stderr, "some text", use_timestamp=True),
    ]


def test_progress_in_quiet_mode(get_initiated_emitter):
    """Only log the message."""
    emitter = get_initiated_emitter(EmitterMode.QUIET)
    emitter.progress("some text")

    assert emitter.printer_calls == [
        call().show(None, "some text", use_timestamp=False, ephemeral=True),
    ]


def test_progress_in_normal_mode(get_initiated_emitter):
    """Send to stderr (ephermeral) and log it."""
    emitter = get_initiated_emitter(EmitterMode.NORMAL)
    emitter.progress("some text")

    assert emitter.printer_calls == [
        call().show(sys.stderr, "some text", use_timestamp=False, ephemeral=True),
    ]


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.VERBOSE,
        EmitterMode.TRACE,
    ],
)
def test_progress_in_verboseish_modes(get_initiated_emitter, mode):
    """Send to stderr (permanent, with timestamp) and log it."""
    emitter = get_initiated_emitter(mode)
    emitter.progress("some text")

    assert emitter.printer_calls == [
        call().show(sys.stderr, "some text", use_timestamp=True, ephemeral=False),
    ]


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.NORMAL,
        EmitterMode.VERBOSE,
        EmitterMode.TRACE,
    ],
)
def test_progressbar_in_useful_modes(get_initiated_emitter, mode):
    """Show the initial message to stderr and init _Progresser correctly."""
    emitter = get_initiated_emitter(mode)
    progresser = emitter.progress_bar("some text", 5000)

    assert emitter.printer_calls == [
        call().show(sys.stderr, "some text", ephemeral=True),
    ]
    assert progresser.total == 5000
    assert progresser.text == "some text"
    assert progresser.stream == sys.stderr
    assert progresser.delta is True


def test_progressbar_with_delta_false(get_initiated_emitter):
    """Init _Progresser with delta=False."""
    emitter = get_initiated_emitter(EmitterMode.QUIET)
    progresser = emitter.progress_bar("some text", 5000, delta=False)
    assert progresser.delta is False


def test_progressbar_in_quiet_mode(get_initiated_emitter):
    """Do not show the initial message (but log it) and init _Progresser with stream in None."""
    emitter = get_initiated_emitter(EmitterMode.QUIET)
    progresser = emitter.progress_bar("some text", 5000)

    assert emitter.printer_calls == [
        call().show(None, "some text", ephemeral=True),
    ]
    assert progresser.stream is None


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.QUIET,
        EmitterMode.NORMAL,
    ],
)
def test_openstream_in_quietish_modes(get_initiated_emitter, mode):
    """Return a stream context manager with the output stream in None."""
    emitter = get_initiated_emitter(mode)

    with patch("craft_cli.messages._StreamContextManager") as stream_context_manager_mock:
        instantiated_cm = object()
        stream_context_manager_mock.return_value = instantiated_cm
        context_manager = emitter.open_stream("some text")

    assert emitter.printer_calls == []
    assert context_manager is instantiated_cm
    assert stream_context_manager_mock.mock_calls == [
        call(emitter._printer, "some text", None),
    ]


@pytest.mark.parametrize(
    "mode",
    [
        EmitterMode.VERBOSE,
        EmitterMode.TRACE,
    ],
)
def test_openstream_in_verboseish_modes(get_initiated_emitter, mode):
    """Return a stream context manager with stderr as the output stream."""
    emitter = get_initiated_emitter(mode)

    with patch("craft_cli.messages._StreamContextManager") as stream_context_manager_mock:
        instantiated_cm = object()
        stream_context_manager_mock.return_value = instantiated_cm
        context_manager = emitter.open_stream("some text")

    assert emitter.printer_calls == []
    assert context_manager is instantiated_cm
    assert stream_context_manager_mock.mock_calls == [
        call(emitter._printer, "some text", sys.stderr),
    ]


# -- tests for stopping the machinery ok


def test_ended_ok(get_initiated_emitter):
    """Finish everything ok."""
    emitter = get_initiated_emitter(EmitterMode.QUIET)
    emitter.ended_ok()

    assert emitter.printer_calls == [call().stop()]


def test_ended_double_after_ok(get_initiated_emitter):
    """Support double ending."""
    emitter = get_initiated_emitter(EmitterMode.QUIET)
    emitter.ended_ok()
    emitter.printer_calls.clear()

    emitter.ended_ok()
    assert emitter.printer_calls == []


def test_ended_double_after_error(get_initiated_emitter):
    """Support double ending."""
    emitter = get_initiated_emitter(EmitterMode.QUIET)
    emitter.error(CraftError("test message"))
    emitter.printer_calls.clear()

    emitter.ended_ok()
    assert emitter.printer_calls == []


# -- tests for error reporting


@pytest.mark.parametrize("mode", [EmitterMode.QUIET, EmitterMode.NORMAL])
def test_reporterror_simple_message_only_quietish(mode, get_initiated_emitter):
    """Report just a simple message, in silent modes."""
    emitter = get_initiated_emitter(mode)
    error = CraftError("test message")
    emitter.error(error)

    full_log_message = f"Full execution log: {repr(emitter._log_filepath)}"
    assert emitter.printer_calls == [
        call().show(sys.stderr, "test message", use_timestamp=False, end_line=True),
        call().show(sys.stderr, full_log_message, use_timestamp=False, end_line=True),
        call().stop(),
    ]


@pytest.mark.parametrize("mode", [EmitterMode.VERBOSE, EmitterMode.TRACE])
def test_reporterror_simple_message_only_verboseish(mode, get_initiated_emitter):
    """Report just a simple message, in more verbose modes."""
    emitter = get_initiated_emitter(mode)
    error = CraftError("test message")
    emitter.error(error)

    full_log_message = f"Full execution log: {repr(emitter._log_filepath)}"
    assert emitter.printer_calls == [
        call().show(sys.stderr, "test message", use_timestamp=True, end_line=True),
        call().show(sys.stderr, full_log_message, use_timestamp=True, end_line=True),
        call().stop(),
    ]


@pytest.mark.parametrize("mode", [EmitterMode.QUIET, EmitterMode.NORMAL])
def test_reporterror_detailed_info_quietish(mode, get_initiated_emitter):
    """Report an error having detailed information, in silent modes."""
    emitter = get_initiated_emitter(mode)
    error = CraftError("test message", details="boom")
    emitter.error(error)

    full_log_message = f"Full execution log: {repr(emitter._log_filepath)}"
    assert emitter.printer_calls == [
        call().show(sys.stderr, "test message", use_timestamp=False, end_line=True),
        call().show(None, "Detailed information: boom", use_timestamp=False, end_line=True),
        call().show(sys.stderr, full_log_message, use_timestamp=False, end_line=True),
        call().stop(),
    ]


@pytest.mark.parametrize("mode", [EmitterMode.VERBOSE, EmitterMode.TRACE])
def test_reporterror_detailed_info_verboseish(mode, get_initiated_emitter):
    """Report an error having detailed information, in more verbose modes."""
    emitter = get_initiated_emitter(mode)
    error = CraftError("test message", details="boom")
    emitter.error(error)

    full_log_message = f"Full execution log: {repr(emitter._log_filepath)}"
    assert emitter.printer_calls == [
        call().show(sys.stderr, "test message", use_timestamp=True, end_line=True),
        call().show(sys.stderr, "Detailed information: boom", use_timestamp=True, end_line=True),
        call().show(sys.stderr, full_log_message, use_timestamp=True, end_line=True),
        call().stop(),
    ]


@pytest.mark.parametrize("mode", [EmitterMode.QUIET, EmitterMode.NORMAL])
def test_reporterror_chained_exception_quietish(mode, get_initiated_emitter):
    """Report an error that was originated after other exception, in silent modes."""
    emitter = get_initiated_emitter(mode)
    try:
        try:
            raise ValueError("original")
        except ValueError as err:
            orig_exception = err
            raise CraftError("test message") from err
    except CraftError as err:
        error = err

    with patch("craft_cli.messages._get_traceback_lines") as tblines_mock:
        tblines_mock.return_value = ["traceback line 1", "traceback line 2"]
        emitter.error(error)

    full_log_message = f"Full execution log: {repr(emitter._log_filepath)}"
    assert emitter.printer_calls == [
        call().show(sys.stderr, "test message", use_timestamp=False, end_line=True),
        call().show(None, "traceback line 1", use_timestamp=False, end_line=True),
        call().show(None, "traceback line 2", use_timestamp=False, end_line=True),
        call().show(sys.stderr, full_log_message, use_timestamp=False, end_line=True),
        call().stop(),
    ]

    # check the traceback lines are generated using the original exception
    tblines_mock.assert_called_with(orig_exception)  # type: ignore


@pytest.mark.parametrize("mode", [EmitterMode.VERBOSE, EmitterMode.TRACE])
def test_reporterror_chained_exception_verboseish(mode, get_initiated_emitter):
    """Report an error that was originated after other exception, in more verbose modes."""
    emitter = get_initiated_emitter(mode)
    try:
        try:
            raise ValueError("original")
        except ValueError as err:
            orig_exception = err
            raise CraftError("test message") from err
    except CraftError as err:
        error = err

    with patch("craft_cli.messages._get_traceback_lines") as tblines_mock:
        tblines_mock.return_value = ["traceback line 1", "traceback line 2"]
        emitter.error(error)

    full_log_message = f"Full execution log: {repr(emitter._log_filepath)}"
    assert emitter.printer_calls == [
        call().show(sys.stderr, "test message", use_timestamp=True, end_line=True),
        call().show(sys.stderr, "traceback line 1", use_timestamp=True, end_line=True),
        call().show(sys.stderr, "traceback line 2", use_timestamp=True, end_line=True),
        call().show(sys.stderr, full_log_message, use_timestamp=True, end_line=True),
        call().stop(),
    ]

    # check the traceback lines are generated using the original exception
    tblines_mock.assert_called_with(orig_exception)  # type: ignore


@pytest.mark.parametrize("mode", [EmitterMode.QUIET, EmitterMode.NORMAL])
def test_reporterror_with_resolution_quietish(mode, get_initiated_emitter):
    """Report an error with a recommended resolution, in silent modes."""
    emitter = get_initiated_emitter(mode)
    error = CraftError("test message", resolution="run")
    emitter.error(error)

    full_log_message = f"Full execution log: {repr(emitter._log_filepath)}"
    assert emitter.printer_calls == [
        call().show(sys.stderr, "test message", use_timestamp=False, end_line=True),
        call().show(sys.stderr, "Recommended resolution: run", use_timestamp=False, end_line=True),
        call().show(sys.stderr, full_log_message, use_timestamp=False, end_line=True),
        call().stop(),
    ]


@pytest.mark.parametrize("mode", [EmitterMode.VERBOSE, EmitterMode.TRACE])
def test_reporterror_with_resolution_verboseish(mode, get_initiated_emitter):
    """Report an error with a recommended resolution, in more verbose modes."""
    emitter = get_initiated_emitter(mode)
    error = CraftError("test message", resolution="run")
    emitter.error(error)

    full_log_message = f"Full execution log: {repr(emitter._log_filepath)}"
    assert emitter.printer_calls == [
        call().show(sys.stderr, "test message", use_timestamp=True, end_line=True),
        call().show(sys.stderr, "Recommended resolution: run", use_timestamp=True, end_line=True),
        call().show(sys.stderr, full_log_message, use_timestamp=True, end_line=True),
        call().stop(),
    ]


@pytest.mark.parametrize("mode", [EmitterMode.QUIET, EmitterMode.NORMAL])
def test_reporterror_with_docs_quietish(mode, get_initiated_emitter):
    """Report including a docs url, in silent modes."""
    emitter = get_initiated_emitter(mode)
    error = CraftError("test message", docs_url="https://charmhub.io/docs/whatever")
    emitter.error(error)

    full_log_message = f"Full execution log: {repr(emitter._log_filepath)}"
    full_docs_message = "For more information, check out: https://charmhub.io/docs/whatever"
    assert emitter.printer_calls == [
        call().show(sys.stderr, "test message", use_timestamp=False, end_line=True),
        call().show(sys.stderr, full_docs_message, use_timestamp=False, end_line=True),
        call().show(sys.stderr, full_log_message, use_timestamp=False, end_line=True),
        call().stop(),
    ]


@pytest.mark.parametrize("mode", [EmitterMode.VERBOSE, EmitterMode.TRACE])
def test_reporterror_with_docs_verboseish(mode, get_initiated_emitter):
    """Report including a docs url, in more verbose modes."""
    emitter = get_initiated_emitter(mode)
    error = CraftError("test message", docs_url="https://charmhub.io/docs/whatever")
    emitter.error(error)

    full_log_message = f"Full execution log: {repr(emitter._log_filepath)}"
    full_docs_message = "For more information, check out: https://charmhub.io/docs/whatever"
    assert emitter.printer_calls == [
        call().show(sys.stderr, "test message", use_timestamp=True, end_line=True),
        call().show(sys.stderr, full_docs_message, use_timestamp=True, end_line=True),
        call().show(sys.stderr, full_log_message, use_timestamp=True, end_line=True),
        call().stop(),
    ]


def test_reporterror_full_complete(get_initiated_emitter):
    """Sanity case to check order between the different parts."""
    emitter = get_initiated_emitter(EmitterMode.TRACE)
    try:
        try:
            raise ValueError("original")
        except ValueError as err:
            raise CraftError(
                "test message",
                details="boom",
                resolution="run",
                docs_url="https://charmhub.io/docs/whatever",
            ) from err
    except CraftError as err:
        error = err

    with patch("craft_cli.messages._get_traceback_lines") as tblines_mock:
        tblines_mock.return_value = ["traceback line 1", "traceback line 2"]
        emitter.error(error)

    full_log_message = f"Full execution log: {repr(emitter._log_filepath)}"
    full_docs_message = "For more information, check out: https://charmhub.io/docs/whatever"
    assert emitter.printer_calls == [
        call().show(sys.stderr, "test message", use_timestamp=True, end_line=True),
        call().show(sys.stderr, "Detailed information: boom", use_timestamp=True, end_line=True),
        call().show(sys.stderr, "traceback line 1", use_timestamp=True, end_line=True),
        call().show(sys.stderr, "traceback line 2", use_timestamp=True, end_line=True),
        call().show(sys.stderr, "Recommended resolution: run", use_timestamp=True, end_line=True),
        call().show(sys.stderr, full_docs_message, use_timestamp=True, end_line=True),
        call().show(sys.stderr, full_log_message, use_timestamp=True, end_line=True),
        call().stop(),
    ]


def test_reporterror_double_after_ok(get_initiated_emitter):
    """Support error reporting after ending."""
    emitter = get_initiated_emitter(EmitterMode.TRACE)
    emitter.ended_ok()
    emitter.printer_calls.clear()

    emitter.error(CraftError("test message"))
    assert emitter.printer_calls == []


def test_reporterror_double_after_error(get_initiated_emitter):
    """Support error reporting after ending."""
    emitter = get_initiated_emitter(EmitterMode.TRACE)
    emitter.error(CraftError("test message"))
    emitter.printer_calls.clear()

    emitter.error(CraftError("test message"))
    assert emitter.printer_calls == []
