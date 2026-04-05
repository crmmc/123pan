# Technology Stack

**Project:** 123pan Desktop Client - Folder Upload & Drag-Drop Enhancement
**Researched:** 2026-04-05

## Recommended Stack

### No New Dependencies Required

The existing stack already contains everything needed for folder upload and drag-drop. No additional libraries should be added.

| Technology | Version | Purpose | Confidence |
|------------|---------|---------|------------|
| PyQt6 `QWidget.setAcceptDrops` | 6.10.2 | Enable drag-drop on the file interface widget | HIGH |
| PyQt6 `QEvent.Type.DragEnter/DragMove/Drop` | 6.10.2 | Drag-drop event lifecycle handling | HIGH |
| PyQt6 `QMimeData.hasUrls()` / `urls()` | 6.10.2 | Extract local file/folder paths from drop events | HIGH |
| PyQt6 `QUrl.isLocalFile()` / `toLocalFile()` | 6.10.2 | Resolve dropped URLs to local filesystem paths | HIGH |
| PyQt6 `QFileDialog.getExistingDirectory()` | 6.10.2 | Folder picker dialog for button-based folder upload | HIGH |
| `pathlib.Path.is_dir()` | stdlib | Detect whether dropped path is a file or folder | HIGH |
| `Pan123.prepare_folder_upload()` | existing | Recursively creates remote directories, returns upload plan | HIGH |
| `FileInterface.PrepareUploadTask` | existing | Background task that handles both file and folder uploads | HIGH |

## Why No New Libraries

### Drag-and-Drop: Already Implemented

The codebase already has a complete drag-drop implementation in `file_interface.py` (lines 191-269):

1. `setAcceptDrops(True)` called in `__initWidget()` (line 191)
2. `eventFilter` intercepts viewport events (lines 199-202)
3. `dragEnterEvent`, `dragMoveEvent`, `dropEvent` delegate to `__handleDropEvent` (lines 204-217)
4. `__extractLocalPaths` uses `QMimeData.hasUrls()` / `urls()` + `QUrl.isLocalFile()` / `toLocalFile()` to extract `Path` objects (lines 253-269)
5. `__dropLocalPaths` passes paths to `__prepareLocalUploads` (lines 245-251)
6. `__prepareLocalUploads` runs `PrepareUploadTask` on `QThreadPool` (lines 841-857)
7. `PrepareUploadTask.run()` detects `path.is_dir()`, calls `pan.prepare_folder_upload()` for folders (lines 459-494)

This already handles both file and folder drops correctly. No external drag-drop library is needed.

### Folder Upload Button: One API Call

Adding a "select folder" button requires exactly one new Qt API:

```python
folder_path = QFileDialog.getExistingDirectory(self, "选择要上传的文件夹")
```

This is already available in PyQt6 6.10.2. `QFileDialog.getExistingDirectory` is used in `setting_interface.py` line 201 for download path selection, so the pattern is established in the codebase.

### Why NOT Use External Libraries

| Library | Why Not |
|---------|---------|
| `pythondnd` / `tkinterdnd2` | Tkinter-based, incompatible with Qt. Irrelevant. |
| Any drag-drop pip package | PyQt6 has native drag-drop support via `QMimeData`, `QDragEnterEvent`, `QDropEvent`. External libraries add complexity with zero benefit. |
| `watchdog` for folder monitoring | Folder upload is a one-shot action (select folder -> upload contents), not sync. No monitoring needed. |
| `pathlib` alternatives (`glob`, `os.walk`) | `os.walk` is already used inside `prepare_folder_upload()` and works correctly. No change needed. |

## What Needs to Change

The stack is complete. The implementation gap is minor:

### 1. Add Folder Upload Button Handler (~5 lines)

In `file_interface.py`, the `__uploadFile` method (line 833) currently only uses `QFileDialog.getOpenFileNames`. A parallel method or menu option needs `QFileDialog.getExistingDirectory`:

```python
def __uploadFolder(self):
    folder_path = QFileDialog.getExistingDirectory(self, "选择要上传的文件夹")
    if folder_path:
        self.__prepareLocalUploads([Path(folder_path)])
```

`__prepareLocalUploads` already handles both files and folders via `PrepareUploadTask`.

### 2. UI: Add Folder Upload Button or Menu Entry

Either a new `PushButton` in `__createTopBar` or a dropdown on the existing upload button. The existing upload button is at line 88.

### 3. Drag-Drop: Already Works for Folders

No changes needed. The event chain `dropEvent -> __handleDropEvent -> __dropLocalPaths -> __extractLocalPaths -> __prepareLocalUploads -> PrepareUploadTask` already detects `is_dir()` and calls `prepare_folder_upload()`.

## Verification

| Capability | Verified | Evidence |
|------------|----------|----------|
| PyQt6 drag-drop API exists | YES | Runtime check: `QEvent.Type.DragEnter=60, DragMove=61, Drop=63` |
| `QMimeData.hasUrls()` works | YES | Runtime check confirmed |
| `QUrl.isLocalFile()` / `toLocalFile()` work | YES | Runtime check: `/tmp/test` resolved correctly |
| `QFileDialog.getExistingDirectory` exists | YES | Runtime check confirmed; already used in `setting_interface.py:201` |
| `Path.is_dir()` detects folders | YES | stdlib, no verification needed |
| `prepare_folder_upload` handles recursive upload | YES | Code review: uses `os.walk`, creates directories via `_create_directory`, returns `file_targets` list |
| `PrepareUploadTask` routes folders correctly | YES | Code review: line 469 `if path.is_dir(): plan = self.pan.prepare_folder_upload(...)` |

## Installation

```bash
# No new packages needed. Existing install:
uv sync
```

## Sources

- PyQt6 6.10.2 runtime verification on this machine
- Codebase analysis: `src/app/view/file_interface.py` (drag-drop + upload flow)
- Codebase analysis: `src/app/common/api.py` (`prepare_folder_upload`, `ensure_directory`)
- Codebase analysis: `src/app/view/setting_interface.py` (existing `getExistingDirectory` usage)
