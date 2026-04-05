# Domain Pitfalls: Folder Upload for 123pan Desktop Client

**Domain:** PyQt6 cloud storage desktop client -- adding folder upload/drag-drop
**Researched:** 2026-04-05
**Codebase analyzed:** api.py, file_interface.py, transfer_interface.py, database.py, download_resume.py

---

## Critical Pitfalls

Mistakes that cause rewrites, data corruption, or user-facing failures.

### Pitfall 1: Blocking UI During os.walk Traversal

**What goes wrong:** Walking a large directory tree (e.g., `node_modules`, `.git`) on the main thread freezes the GUI for seconds or minutes. The `file_interface.py` drag-drop handler (`__dropLocalPaths` -> `__prepareLocalUploads` -> `PrepareUploadTask.run`) already offloads to `QThreadPool`, but the existing `prepare_folder_upload` in `api.py` (line 564) calls `os.walk` synchronously and also makes network calls to create directories inside the same loop.

**Why it happens:** The directory traversal and remote directory creation are coupled in a single method. `os.walk` on a folder with tens of thousands of files produces a large list, and every subdirectory triggers an HTTP POST to `/a/api/file/upload_request`.

**Consequences:** The `QThreadPool` worker thread is occupied for the entire preparation phase. If the user drops a large folder, the thread pool (default `QThreadPool.globalInstance()`) is blocked, preventing other background tasks like file list loading (`LoadListTask`) from running.

**Prevention:**
- Separate local traversal from remote directory creation. Walk the local tree first (fast, pure I/O), then create remote directories in batches.
- Add a file count/size limit check before starting. If a folder exceeds a threshold (e.g., 10,000 files), warn the user.
- Skip hidden directories (`.git`, `.DS_Store`, `__pycache__`) and symlinks by default during traversal.

**Detection:** Drop a `node_modules` folder or a folder with 5000+ files. If the UI becomes unresponsive or the transfer table takes more than a few seconds to populate, this pitfall has been hit.

**Phase:** Phase 1 (Folder Traversal & Directory Creation) -- must be addressed at the design level before any upload code is written.

---

### Pitfall 2: Parent Directory Must Exist Before Children

**What goes wrong:** Files are enqueued for upload before their parent directories have been created on the remote server. The upload API requires `parentFileId` for each file, but if the directory creation is still in progress or failed, the file upload will fail with an error.

**Why it happens:** The existing `prepare_folder_upload` in `api.py` (line 564-612) does create directories first via `os.walk` (directories are yielded before their children), and `dir_names.sort()` is called. However, the `file_targets` list is returned as a flat list without any ordering guarantee that matches directory creation order. More critically, if directory creation for a nested folder fails mid-way (line 594 raises `RuntimeError`), the entire preparation aborts, but partial directories are already created on the server with no cleanup.

**Consequences:** Orphaned empty directories on the remote server. If a retry happens, the directory name conflict logic (`_choose_available_directory_name`) may create duplicate directories like `myfolder(1)`.

**Prevention:**
- Create directories strictly depth-first (parents before children). `os.walk` with `topdown=True` (the default) handles this naturally.
- After creating each directory, verify the returned `FileId` before proceeding to children.
- If any directory creation fails, record which directories were successfully created so the retry can skip them (using `ensure_directory` which already checks for existence).
- Do not return file targets until ALL directories are confirmed created.

**Detection:** Test with a deeply nested folder structure (5+ levels). Kill the network mid-preparation and observe whether orphaned directories remain.

**Phase:** Phase 1 (Directory Creation) -- this is the core logic of folder upload preparation.

---

### Pitfall 3: API Rate Limiting (429) During Batch Directory Creation

**What goes wrong:** Creating hundreds of directories in rapid succession triggers 429 rate limiting from the 123pan API. The upload code already handles 429 for S3 part uploads (see `upload_file_stream` line 852-873), but `prepare_folder_upload` makes sequential POST calls to `_create_directory` with no rate limiting or backoff.

**Why it happens:** Each `_create_directory` call is a synchronous `self.session.post` with a 10-second timeout. For a folder with 200 subdirectories, that is 200 API calls in quick succession.

**Consequences:** Random directory creation failures, partial folder structures, and a confusing user experience where some uploads succeed and others fail with no clear pattern.

**Prevention:**
- Add a small delay (100-200ms) between directory creation API calls.
- Implement exponential backoff on 429 responses specifically for directory creation.
- Consider batching: create top-level directories first, pause, then create nested ones.
- Reuse the existing `Retry` adapter from the `requests` session, but note it only retries on connection errors, not on 429 status codes (since `raise_on_status=False` is set at line 57 in api.py).

**Detection:** Create a test folder with 50+ subdirectories and upload it. Watch for sporadic 429 errors in the log.

**Phase:** Phase 1 (Directory Creation) -- must be implemented alongside the creation logic.

---

### Pitfall 4: Pan123 Instance Thread-Safety Violation

**What goes wrong:** The `Pan123` instance (`self.pan`) is shared between the main thread and multiple background threads. The `prepare_folder_upload` method modifies `self.parent_file_id` indirectly (via `_get_dir_items_by_id` which saves/restores `file_page`), but the save/restore pattern is not thread-safe -- another thread could modify these fields between save and restore.

**Why it happens:** `file_interface.py` line 417-427 shows a cached_state save/restore pattern, and `api.py` line 518-525 shows the same. But these are not atomic. The `_get_dir_items_by_id` method temporarily sets `self.file_page = 0`, and if another thread reads `self.pan.file_page` at that moment, it gets a corrupted value.

**Consequences:** Wrong file listings, corrupted pagination state, or API errors. This is an existing issue in the codebase, but folder upload makes it worse because `prepare_folder_upload` calls `_get_child_directory_map` -> `_get_dir_items_by_id` on the shared `pan` instance from a background thread.

**Prevention:**
- Do NOT mutate `self.pan` state in background threads. Instead, pass the required auth headers and session to a standalone function.
- For folder upload preparation, extract the necessary auth information (headers, session) and call the API directly without touching the shared Pan123 instance state.
- The existing `_create_directory` method (line 484) already takes `parent_id` as a parameter and does not mutate `self.parent_file_id`, which is good. But `_get_dir_items_by_id` still uses instance state.

**Detection:** Run concurrent uploads to different directories while browsing the file list. Watch for wrong file listings or API errors.

**Phase:** Phase 1 -- must be resolved before any folder upload code runs in production. The `PrepareUploadTask` in `file_interface.py` (line 448) already runs on `QThreadPool`, so this is a live bug.

---

### Pitfall 5: Symlink Loops and Special File Traversal

**What goes wrong:** `os.walk` follows symlinks by default on some platforms, and circular symlinks (e.g., a symlink pointing to a parent directory) cause infinite loops. `prepare_folder_upload` uses `os.walk` at line 584 without any symlink or depth protection.

**Why it happens:** macOS and Linux commonly have circular symlinks in `.app` bundles, `node_modules/.bin`, or user-created shortcuts. The default `os.walk` with `followlinks=False` (which is the Python default) does NOT follow symlinks, so this is partially safe. However, the code does not explicitly set `followlinks=False`, meaning a future change could break it.

**Consequences:** Infinite loop during traversal, exhausting memory or hanging the background thread forever.

**Prevention:**
- Explicitly pass `followlinks=False` to `os.walk` (defensive coding).
- Add a maximum depth limit (e.g., 20 levels) to prevent runaway recursion.
- Skip files that are not regular files (skip sockets, FIFOs, device files) by checking `os.path.isfile` or `path.is_file()`.
- Skip hidden directories (names starting with `.`) to avoid `.git`, `.Trash`, and other system directories.

**Detection:** Create a circular symlink (`ln -s .. loop_link`) inside a test folder and attempt to upload it.

**Phase:** Phase 1 (Folder Traversal) -- easy to address early, painful to debug later.

---

## Moderate Pitfalls

### Pitfall 6: Memory Explosion with Large Folder File Lists

**What goes wrong:** `prepare_folder_upload` builds a complete `file_targets` list in memory (line 599-606). For a folder with 100,000 files, each entry contains a dict with 4 keys, consuming significant memory. Combined with the `dir_id_map` and the `top_level_dirs` mapping, this can reach hundreds of MB for very large folders.

**Prevention:** Add a file count limit (e.g., 10,000 files per folder upload). Show a confirmation dialog if the count exceeds a threshold. For extremely large folders, consider streaming the file targets directly to the upload queue instead of accumulating them all first.

**Phase:** Phase 1 -- implement the limit early.

---

### Pitfall 7: No Progress Feedback During Directory Creation

**What goes wrong:** The user drops a folder and sees nothing happening for 10-30 seconds while directories are being created. The `PrepareUploadTask` signal only fires when ALL directories are done. There is no intermediate progress signal for "Creating directory 15/200...".

**Prevention:** Add a progress signal to `PrepareUploadTask` that emits after each directory is created, with a message like "Preparing: 15/200 directories". The UI can show this in a status bar or InfoBar.

**Phase:** Phase 2 (UI Integration) -- after core logic works.

---

### Pitfall 8: Partial Upload Failure with No Recovery

**What goes wrong:** When uploading a folder with 100 files, if file #50 fails, the current code has no mechanism to retry just that file. The user must re-upload the entire folder, which would create duplicate directories (because `_choose_available_directory_name` generates `folder(1)`, `folder(2)` etc.).

**Why it happens:** The upload tasks are added individually to `transfer_interface` (line 872-877 in `file_interface.py`), which is correct -- each file gets its own `UploadTask`. But there is no grouping concept for "all files from the same folder upload". If the user clicks "retry all failed", they cannot distinguish between individual file uploads and folder uploads.

**Prevention:**
- Add a `folder_upload_id` or `batch_id` field to `UploadTask` so the UI can group related uploads.
- When retrying, check if the target directory already exists before re-creating it.
- The existing `ensure_directory` method in `api.py` (line 553) already handles "create if not exists" -- use it for retries.

**Phase:** Phase 2 (Error Recovery) -- after basic folder upload works.

---

### Pitfall 9: Concurrent Upload Slot Exhaustion

**What goes wrong:** Uploading a folder with 500 files fills the upload task queue. The `maxConcurrentUploads` setting (default 3, max 5) means only 3 files upload at a time. But the 497 waiting tasks each occupy a row in the upload table, making it unusable for other uploads.

**Why it happens:** `add_upload_task` in `transfer_interface.py` (line 542) adds each file as a separate task. There is no concept of a "folder upload task" that manages child file uploads.

**Prevention:**
- Consider a parent "Folder Upload" task in the transfer table that expands to show individual files.
- Alternatively, limit the number of visible pending tasks and show a "N more files queued" summary.
- The simpler approach: keep individual tasks but add a "batch cancel" option to cancel all files from the same folder upload.

**Phase:** Phase 2 (UI) -- can be deferred if the table handles 500 rows without performance issues.

---

### Pitfall 10: Token Expiry During Long Folder Uploads

**What goes wrong:** A folder upload with many files can take hours. The 123pan auth token expires during this time. The existing `get_dir_by_id` (line 192-197) handles token expiry by re-login, but the upload flow in `upload_file_stream` does NOT handle token expiry -- it would fail with a cryptic error.

**Prevention:** The `upload_file_stream` method should check for the token-expired response code (code 2) from the 123pan API and trigger a re-login before retrying, similar to how `get_dir_by_id` handles it.

**Phase:** Phase 1 -- critical for reliability of any long-running upload operation.

---

### Pitfall 11: Drag-Drop of Mixed Files and Folders

**What goes wrong:** The user drags a selection containing both files and folders. The existing `PrepareUploadTask.run` (line 460-491 in `file_interface.py`) handles this case correctly -- it checks `path.is_dir()` and branches accordingly. However, if ONE item in the selection fails (e.g., permission denied on a folder), the entire batch fails with an exception that aborts all other items.

**Prevention:** Wrap each item's processing in a try/except. Collect errors separately and report them after processing all items. Successful items should proceed to upload even if some fail.

**Phase:** Phase 1 -- must be handled in the `PrepareUploadTask` implementation.

---

### Pitfall 12: File Modified During Upload Preparation

**What goes wrong:** Between `os.walk` collecting file metadata (size, name) and the actual upload starting, the file could be modified or deleted. The `file_size` captured at line 605 (`(current_path / file_name).stat().st_size`) becomes stale. The upload then fails because the MD5 computed during `upload_file_stream` does not match the expected size.

**Prevention:** This is an inherent race condition. The simplest mitigation is to capture the file size again at upload time (which the existing `upload_file_stream` already does at line 643). The issue is the displayed size in the transfer table may be wrong. Consider updating the task's file_size when the upload actually starts.

**Phase:** Phase 2 -- low priority, cosmetic issue.

---

## Minor Pitfalls

### Pitfall 13: Platform-Specific Path Handling

**What goes wrong:** On Windows, paths use backslashes and may contain Unicode characters. The existing `upload_file_stream` does `file_path.replace("\\", "/")` (line 636), which is a fragile approach. For folder uploads, the `os.walk` output uses native path separators.

**Prevention:** Use `pathlib.Path` consistently throughout (already mostly done in the codebase). The `Path.relative_to()` call at line 588 handles this correctly.

**Phase:** Phase 1 -- verify all path handling uses `pathlib.Path`.

---

### Pitfall 14: File Permission Errors on Traversal

**What goes wrong:** `os.walk` may encounter directories or files that the current user cannot read. On macOS, this can happen with `.Trash`, `.DocumentRevisions-V100`, or Time Machine volumes. The default `os.walk` raises `PermissionError`.

**Prevention:** Either catch `PermissionError` in the traversal loop and skip inaccessible items, or set `os.walk(..., onerror=lambda e: None)` to silently skip them.

**Phase:** Phase 1 -- add error handling to the walk loop.

---

### Pitfall 15: Empty Folders Not Created

**What goes wrong:** `os.walk` does not yield directories that contain no files and no subdirectories (actually it does yield them, but they have empty `dir_names` and `file_names`). The current `prepare_folder_upload` correctly creates all directories encountered by `os.walk`. However, if a folder is truly empty (no files, no subdirs), `os.walk` yields it once with empty lists, and the code creates it. This is actually handled correctly by the current implementation.

**Prevention:** Verify with a test case containing empty nested folders. This is listed as a minor pitfall mainly as a reminder to test this edge case.

**Phase:** Phase 1 -- verify, do not assume.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Folder traversal | Symlink loops, permission errors, hidden dirs (Pitfall 5, 14) | Explicit `followlinks=False`, skip hidden, onerror handler |
| Directory creation API | 429 rate limiting (Pitfall 3) | Inter-request delay, backoff |
| Directory creation ordering | Parent before child (Pitfall 2) | `os.walk` topdown=True + verify each creation |
| Background thread | Pan123 shared state mutation (Pitfall 4) | Do not touch instance state from threads |
| Long-running upload | Token expiry (Pitfall 10) | Re-login on code 2 in upload flow |
| Mixed drag-drop | Single failure aborts batch (Pitfall 11) | Per-item error handling |
| Large folders | Memory / UI table performance (Pitfall 6, 9) | File count limit, batch grouping |
| User feedback | No progress during preparation (Pitfall 7) | Intermediate progress signal |
| Error recovery | Orphaned directories, no retry for folder uploads (Pitfall 8) | Batch ID, ensure_directory for retries |

## Sources

- Direct codebase analysis of api.py, file_interface.py, transfer_interface.py, database.py
- 123pan API behavior inferred from api.py implementation (429 handling at line 852, token expiry at line 192-197)
- PyQt6 threading model: QThreadPool + pyqtSignal for thread-safe UI updates
- Python os.walk documentation: default `followlinks=False`, `topdown=True`
- Existing `prepare_folder_upload` implementation (api.py line 564-612) as the primary code to extend

## Confidence Assessment

| Pitfall | Confidence | Source |
|---------|------------|--------|
| Blocking UI (P1) | HIGH | Code shows QThreadPool usage but coupled traversal+API calls |
| Parent-before-child (P2) | HIGH | `os.walk` ordering is well-documented, existing code uses it correctly |
| Rate limiting (P3) | HIGH | Existing upload code shows 429 handling; directory creation lacks it |
| Thread safety (P4) | HIGH | Save/restore pattern is visible in code, not atomic |
| Symlink loops (P5) | MEDIUM | Python default is `followlinks=False` but not explicitly set |
| Memory (P6) | HIGH | Standard concern for large in-memory lists |
| No progress (P7) | HIGH | Signal only fires on completion in current code |
| Partial failure (P8) | HIGH | No batch/grouping concept in current task model |
| Upload slots (P9) | MEDIUM | Depends on how many files user uploads; table performance varies |
| Token expiry (P10) | HIGH | Upload code lacks the re-login that list code has |
| Mixed drag-drop (P11) | HIGH | Single try/except wrapping entire batch in current code |
