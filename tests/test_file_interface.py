from pathlib import Path
from unittest.mock import MagicMock, patch

from PyQt6.QtCore import QEvent

from src.app.view.file_interface import FileInterface


class _FakeUrl:
    def __init__(self, local_file="", is_local=True):
        self._local_file = local_file
        self._is_local = is_local

    def isLocalFile(self):
        return self._is_local

    def toLocalFile(self):
        return self._local_file


class _FakeMimeData:
    def __init__(self, urls):
        self._urls = urls

    def hasUrls(self):
        return bool(self._urls)

    def urls(self):
        return self._urls


def test_extract_local_paths_filters_non_local_and_duplicates(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_text("a", encoding="utf-8")
    folder_path = tmp_path / "folder"
    folder_path.mkdir()

    mime_data = _FakeMimeData(
        [
            _FakeUrl(str(file_path)),
            _FakeUrl(str(file_path)),
            _FakeUrl(str(folder_path)),
            _FakeUrl("https://example.com/demo", is_local=False),
            _FakeUrl(""),
        ]
    )

    paths = FileInterface._FileInterface__extractLocalPaths(mime_data)

    assert paths == [file_path, folder_path]


def test_build_upload_summary_handles_empty_folder_upload():
    summary = FileInterface._FileInterface__buildUploadSummary(0, 3)

    assert summary == "已创建 3 个文件夹"


@patch("src.app.view.file_interface.QFileDialog.getExistingDirectory")
def test_upload_folder_calls_prepare_with_selected_path(mock_dialog):
    mock_dialog.return_value = "/some/folder"
    mock_prepare = MagicMock()

    fi = MagicMock()
    fi._FileInterface__prepareLocalUploads = mock_prepare
    FileInterface._FileInterface__uploadFolder(fi)

    mock_prepare.assert_called_once_with([Path("/some/folder")])


@patch("src.app.view.file_interface.QFileDialog.getExistingDirectory")
def test_upload_folder_cancel_does_not_call_prepare(mock_dialog):
    mock_dialog.return_value = ""
    mock_prepare = MagicMock()

    fi = MagicMock()
    fi._FileInterface__prepareLocalUploads = mock_prepare
    FileInterface._FileInterface__uploadFolder(fi)

    mock_prepare.assert_not_called()


def test_drag_highlight_sets_stylesheet_on_enter():
    fi = MagicMock()
    fi.fileTable = MagicMock()
    viewport_mock = MagicMock()
    fi.fileTable.viewport.return_value = viewport_mock
    fi._FileInterface__acceptLocalDrop = MagicMock(return_value=True)

    event = MagicMock()
    event.type.return_value = QEvent.Type.DragEnter

    result = FileInterface._FileInterface__handleDropEvent(fi, event)

    assert result is True
    viewport_mock.setStyleSheet.assert_called_once_with(
        "border: 2px dashed #0078d4; border-radius: 8px;"
    )


def test_drag_highlight_clears_on_leave():
    fi = MagicMock()
    fi.fileTable = MagicMock()
    viewport_mock = MagicMock()
    fi.fileTable.viewport.return_value = viewport_mock

    event = MagicMock()
    event.type.return_value = QEvent.Type.DragLeave

    result = FileInterface._FileInterface__handleDropEvent(fi, event)

    assert result is False
    viewport_mock.setStyleSheet.assert_called_once_with("")


def test_drag_highlight_clears_on_drop():
    fi = MagicMock()
    fi.fileTable = MagicMock()
    viewport_mock = MagicMock()
    fi.fileTable.viewport.return_value = viewport_mock
    fi._FileInterface__dropLocalPaths = MagicMock(return_value=True)

    event = MagicMock()
    event.type.return_value = QEvent.Type.Drop

    result = FileInterface._FileInterface__handleDropEvent(fi, event)

    assert result is True
    viewport_mock.setStyleSheet.assert_called_once_with("")
