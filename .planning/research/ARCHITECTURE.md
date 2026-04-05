# Architecture Patterns: Folder Upload Integration

**Domain:** Desktop cloud storage client (brownfield)
**Researched:** 2026-04-05
**Confidence:** HIGH (based on direct codebase analysis)

## Current Architecture Recap

The existing system follows MVC with Qt Signals/Slots for cross-thread communication:

```
FileInterface (View)
  |  drag/button trigger
  v
PrepareUploadTask (QRunnable, background thread)
  |  calls Pan123.prepare_folder_upload() for directories
  |  calls Pan123.upload_file_stream() via UploadThread
  v
TransferInterface (View + Controller)
  |  manages UploadTask / DownloadTask lifecycle
  |  concurrency control (maxConcurrentUploads)
  v
UploadThread (QThread)
  |  delegates to Pan123.upload_file_stream()
  v
Pan123 (API Client)
  |  REST calls to 123pan
  |  multi-part S3 upload with presigned URLs
  v
Database (SQLite persistence)
```

**Key observation:** The codebase already has partial folder upload support. `Pan123.prepare_folder_upload()` (api.py line 564) handles directory creation on the remote side and returns a flat list of `file_targets`. The `PrepareUploadTask` in `file_interface.py` (line 448) already distinguishes between files and directories when processing dropped paths.

## Recommended Architecture for Folder Upload

The integration is narrower than a greenfield design. The architecture changes fall into three areas: UI entry points, a small orchestration layer, and correctness hardening.

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| FileInterface | Drag-drop handling, upload button, folder selection dialog | TransferInterface (via add_upload_task), PrepareUploadTask |
| PrepareUploadTask (existing) | Background: calls prepare_folder_upload, flattens to file list | FileInterface (via signals) |
| Pan123.prepare_folder_upload (existing) | Remote directory creation, file upload plan generation | 123pan REST API |
| TransferInterface | Upload task queue, concurrency, progress display | UploadThread, Database |
| UploadThread (existing) | Per-file upload execution with pause/cancel/resume | TransferInterface (via signals), Pan123 |
| Pan123.upload_file_stream (existing) | Single file multi-part upload | 123pan REST API, S3 |

### Data Flow: Folder Upload

```
User drags folder / clicks "upload folder" button
  |
  v
FileInterface.__prepareLocalUploads(local_paths)
  |  (runs PrepareUploadTask on QThreadPool)
  v
PrepareUploadTask.run()
  |  for each path in local_paths:
  |    if path.is_dir():
  |      plan = Pan123.prepare_folder_upload(path, target_dir_id)
  |      uploads.extend(plan["file_targets"])
  |    else:
  |      uploads.append(single file entry)
  |
  |  emits finished(uploads, created_dir_count, folder_items, error)
  v
FileInterface.__onPrepareUploadFinished()
  |  for each upload in uploads:
  |    TransferInterface.add_upload_task(...)
  |  refreshes tree + file list
  v
TransferInterface manages each file as individual UploadTask
  |  (existing concurrency, pause, cancel, resume logic applies)
  v
UploadThread per file -> Pan123.upload_file_stream()
```

**This flow already exists in the codebase.** The prepare_folder_upload method (api.py:564-612) walks the local directory tree with os.walk, creates remote directories via _create_directory, and returns a flat list of {file_name, local_path, target_dir_id, file_size} dicts. The PrepareUploadTask (file_interface.py:448-494) calls this and feeds results to the transfer interface.

## What Actually Needs to Change

### 1. UI Entry Point: Folder Selection Button (NEW)

**File:** `src/app/view/file_interface.py`

The upload button currently calls `__uploadFile()` which uses `QFileDialog.getOpenFileNames()` -- file-only selection. Need a new method that uses `QFileDialog.getExistingDirectory()` for folder selection.

**Change:**
- Add a new button or modify the existing upload button to offer a menu: "Upload Files" / "Upload Folder"
- Alternatively, add a separate "Upload Folder" button next to the existing upload button

**Recommended approach:** Replace the single upload button with a dropdown/split button that offers both options. This keeps the toolbar compact while providing clear access to folder upload.

```python
# In __createTopBar, replace uploadButton with:
from qfluentwidgets import ToolButton, RoundMenu, Action

self.uploadButton = ToolButton(FIF.UP.icon(), self.topBarFrame)
upload_menu = RoundMenu(parent=self)
upload_menu.addAction(Action(FIF.FILE.icon(), "Upload Files", triggered=self.__uploadFile))
upload_menu.addAction(Action(FIF.FOLDER.icon(), "Upload Folder", triggered=self.__uploadFolder))
self.uploadButton.setMenu(upload_menu)
```

**New method:**
```python
def __uploadFolder(self):
    folder_path = QFileDialog.getExistingDirectory(self, "Select folder to upload")
    if folder_path:
        self.__prepareLocalUploads([Path(folder_path)])
```

### 2. Drag-Drop: Already Works

The drag-drop handler (`__dropLocalPaths`, `__prepareLocalUploads`) already processes both files and directories through `PrepareUploadTask`. When a folder is dropped, `PrepareUploadTask.run()` detects `path.is_dir()` and calls `prepare_folder_upload`. No changes needed.

### 3. Pan123.prepare_folder_upload: Hardening (EXISTING, may need fixes)

**File:** `src/app/common/api.py` (lines 564-612)

Current implementation:
- Uses `os.walk` to traverse local directory tree
- Creates remote directories breadth-first during walk
- Returns flat file list with correct `target_dir_id` per file

**Potential issues to address:**

1. **Error recovery:** If directory creation fails mid-way, some remote directories are already created with no cleanup. Consider wrapping in try/except with rollback or at minimum logging the partial state.

2. **Large directory trees:** For directories with hundreds of subdirectories, the sequential `_create_directory` calls are slow (one HTTP request per directory). This is acceptable as a first implementation but should be documented as a known limitation.

3. **Duplicate handling:** `_choose_available_directory_name` appends `(1)`, `(2)` etc. to avoid name collisions at the root level only. Nested directory name collisions are not handled because `_create_directory` is called without checking existing children first. This should work because the 123pan API likely auto-handles duplicates, but needs verification.

### 4. No New Components Needed

The architecture already supports folder upload end-to-end:
- Directory creation: `Pan123.prepare_folder_upload()` -- exists
- File flattening: `PrepareUploadTask` -- exists
- Per-file upload: `UploadThread` + `Pan123.upload_file_stream()` -- exists
- Progress tracking: `TransferInterface` per-file -- exists
- Persistence: Database already stores upload tasks with `target_dir_id` -- exists

## Patterns to Follow

### Pattern 1: Background Preparation with Signal Callback
**What:** Heavy work (directory traversal, API calls for mkdir) runs on QThreadPool via QRunnable. Results come back to UI thread via pyqtSignal.
**When:** Any operation that blocks on network or filesystem I/O.
**Existing usage:** PrepareUploadTask, LoadListTask, CreateFolderTask, DeleteFileTask all follow this pattern.
**New code must follow this too.**

### Pattern 2: Flat Task Queue for Transfer
**What:** Folder upload produces N individual file upload tasks. Each file becomes its own UploadTask in TransferInterface. The folder structure is resolved during preparation; the transfer layer only knows about files.
**Why:** Reuses existing concurrency control (maxConcurrentUploads), pause/resume, and progress tracking per file. No special "folder task" abstraction needed.
**Trade-off:** Users see individual files in the upload table, not a single folder entry. This is simpler and more informative (per-file progress).

### Pattern 3: No Abstraction for "Folder Upload"
**What:** Folder upload is not a separate entity -- it is a UI interaction that produces multiple file upload tasks plus some remote directory creation.
**Why:** The existing architecture already handles this correctly. Adding a "FolderUploadTask" abstraction would create unnecessary complexity with no benefit.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Blocking UI During Directory Creation
**What:** Calling Pan123.prepare_folder_upload() on the main thread.
**Why bad:** The method makes N sequential HTTP calls (one mkdir per remote directory). For a folder with 50 subdirectories, this blocks the UI for 10+ seconds.
**Instead:** Keep using PrepareUploadTask on QThreadPool (already the pattern).

### Anti-Pattern 2: Single "Folder" Row in Transfer Table
**What:** Showing one row for the entire folder with aggregate progress.
**Why bad:** Cannot pause/resume individual files. Cannot show which file failed. Adds a new abstraction layer that duplicates most of UploadTask logic.
**Instead:** Add each file as its own row. The directory structure is already created; files upload independently.

### Anti-Pattern 3: Recursive Upload in a Single Thread
**What:** Walking the tree and uploading files in the same background task.
**Why bad:** Cannot leverage existing concurrency control. One slow file blocks all subsequent files.
**Instead:** Separate preparation (mkdir + plan) from execution (per-file upload). The existing code already does this.

## Build Order (Phase Dependencies)

Based on the analysis, the implementation phases should be:

```
Phase 1: UI Entry Point (file_interface.py only)
  |
  |  Depends on: nothing new
  |  Enables: user can select folder via button
  |
  v
Phase 2: Verify & Harden prepare_folder_upload (api.py only)
  |
  |  Depends on: Phase 1 (for testing)
  |  Enables: correct behavior on edge cases
  |
  v
Phase 3: UX Polish (file_interface.py, transfer_interface.py)
  |
  |  Depends on: Phase 1
  |  Enables: better user feedback for folder uploads
```

### Phase 1: UI Entry Point
- Modify `__createTopBar()` to add folder upload trigger (dropdown menu or separate button)
- Add `__uploadFolder()` method using `QFileDialog.getExistingDirectory()`
- Call existing `__prepareLocalUploads([Path(folder_path)])`
- **Files changed:** `src/app/view/file_interface.py` only
- **Risk:** LOW -- reuses existing tested code path

### Phase 2: Hardening
- Add error handling for partial directory creation failures
- Verify duplicate name handling at nested levels
- Test with large directory trees (100+ files, deep nesting)
- Test with special characters in filenames
- **Files changed:** `src/app/common/api.py` only
- **Risk:** LOW -- defensive improvements only

### Phase 3: UX Polish (optional, defer if needed)
- Show a summary before starting: "Will upload N files in M folders"
- Group upload rows visually (e.g., prefix with folder name)
- Show folder creation progress during preparation
- **Files changed:** `src/app/view/file_interface.py`, possibly `src/app/view/transfer_interface.py`
- **Risk:** MEDIUM -- touches UI display logic

## Scalability Considerations

| Concern | 10 files | 100 files | 1000 files |
|---------|---------|-----------|------------|
| Directory creation API calls | <1s | 3-10s | 30s+ (rate limit risk) |
| Upload table rows | Fine | Scrollable, fine | UI lag risk, consider virtual scrolling |
| Concurrent upload slots | 3-5 files in parallel | Queue handles it | Queue handles it, total time scales linearly |
| Memory (prepare plan) | Negligible | Negligible | Walk + stat is O(N), fine |

**Key scalability limit:** The sequential mkdir calls during preparation. For 1000+ subdirectories, this could take 30+ seconds. Mitigation: show a progress indicator during preparation phase. Long-term: batch directory creation if the API supports it (unlikely with current 123pan API).

## Summary

**The architecture already supports folder upload.** The critical realization is that `Pan123.prepare_folder_upload()` and `PrepareUploadTask` already implement the full folder-to-files pipeline. The only missing piece is a UI entry point for folder selection (as opposed to drag-drop, which already works).

**No new components, no new abstractions, no database schema changes needed.** The work is primarily a UI change in file_interface.py plus defensive hardening in api.py.

**Recommended build order:** UI entry point first (it can be tested immediately since the backend already works), then hardening, then UX polish.

---

*Architecture analysis: 2026-04-05*
