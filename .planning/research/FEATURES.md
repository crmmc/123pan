# Feature Landscape

**Domain:** Third-party cloud storage desktop client (123pan)
**Researched:** 2026-04-05
**Context:** Brownfield project -- folder upload is the next milestone on top of existing login, file browsing, single-file upload, multi-threaded download, transfer management, and settings.

---

## What Already Exists

Before cataloguing new features, documenting what the codebase already delivers. This avoids duplicating work and establishes the baseline.

| Capability | Implementation | Location |
|------------|---------------|----------|
| Login / auto-login | Pan123.login(), DB token persistence | api.py, database.py |
| File browsing with tree + table | FileInterface with lazy-load tree | file_interface.py |
| Single-file upload (chunked, resumable) | upload_file_stream with S3 multipart | api.py |
| Multi-threaded download (chunked, resumable) | DownloadThread + download_resume | transfer_interface.py |
| Transfer management (pause/resume/retry/cancel) | TransferInterface with task queue | transfer_interface.py |
| Settings (paths, concurrency, retry) | SettingInterface + Database config | setting_interface.py, database.py |
| Drag-drop upload (files AND folders) | eventFilter + __handleDropEvent | file_interface.py |
| Folder upload preparation (API-level) | prepare_folder_upload in Pan123 | api.py |
| Breadcrumb navigation | BreadcrumbBar wired to path_stack | file_interface.py |
| File rename / delete / new folder | Right-click menu + top-bar buttons | file_interface.py |
| Duplicate name handling | _choose_available_directory_name | api.py |
| Storage usage display | Card with progress bar in sidebar | file_interface.py |
| Upload persistence / resume on restart | upload_tasks DB table + reload logic | database.py, transfer_interface.py |

**Key finding:** The backend for folder upload (`prepare_folder_upload`) and the drag-drop pathway that accepts folders already exist. The gap is small and specific.

---

## Table Stakes

Features users expect in a cloud storage client. Missing any = the client feels incomplete.

| # | Feature | Why Expected | Complexity | Gap Analysis | Notes |
|---|---------|-------------|------------|--------------|-------|
| F1 | **Folder upload via button** | Every cloud client has "Upload Folder" in toolbar. Users who do not use drag-drop need this. | Low | `__uploadFile` only opens `getOpenFileNames`. Need to add a "Upload Folder" button or modify upload button to offer both. | QFileDialog.getExistingDirectory is one line. The hard part (prepare_folder_upload) already exists. |
| F2 | **Folder upload progress aggregation** | When uploading 200 files in a folder, users need to see overall progress, not 200 individual rows. | Medium | Current transfer_interface shows per-file rows. No concept of "folder upload group". | Could add a collapsible group row or a summary line. Minimal viable: just show all files as individual tasks (current behavior) with a summary InfoBar. |
| F3 | **Upload button shows both file and folder options** | Users need clear affordance for both actions. | Low | Single "Upload" button only triggers file picker. Need either a split button or a second button. | Split button (dropdown on upload button) or separate "Upload Folder" button. |
| F4 | **Folder upload error handling with partial success** | If 3 of 50 files fail, user must know which 3 failed and be able to retry them. | Medium | Current per-file error handling exists (retry button per task). The missing piece is a clear summary after folder upload completes. | Individual file tasks already support retry. Add a summary notification listing failed files. |
| F5 | **Drag-drop visual feedback** | Users must see where they are dropping and what will happen. | Low | Current drag-drop accepts silently. No visual highlight on the drop zone. | Add stylesheet overlay or border highlight on fileTable during dragEnter. |

---

## Differentiators

Features that elevate the client beyond basic functionality. Not expected, but valued.

| # | Feature | Value Proposition | Complexity | Notes |
|---|---------|-------------------|------------|-------|
| D1 | **Upload folder with file count / size preview** | Before starting a large folder upload, show "150 files, 2.3 GB -- proceed?" | Low | os.walk + stat is fast. A simple confirmation dialog. Prevents accidental uploads. |
| D2 | **Folder upload progress bar in file list** | Show a pseudo-entry in the file table representing the folder being uploaded, with aggregate % | Medium | Requires a "virtual" file entry or a dedicated progress overlay. |
| D3 | **Recursive folder download** | Download an entire folder (as zip or recursively). Currently only single-file download works. | Medium | 123pan API supports folder download (Type=1 returns zip URL). The batch_download_info endpoint is already called in link_by_fileDetail for Type=1. |
| D4 | **File type icons** | Show different icons for images, videos, documents, archives instead of a generic document icon. | Low | Map file extensions to FluentIcon set. |
| D5 | **Batch select and download** | Select multiple files and download them all at once. | Low-Medium | Current selection is SingleSelection. Change to MultiSelection and iterate selected rows. |

---

## Anti-Features

Features to explicitly NOT build. These increase complexity without proportional value for this project's scope.

| Anti-Feature | Why Avoid | What to Do Instead |
|-------------|-----------|-------------------|
| Real-time sync / file watcher | Extremely complex (inotify/fsevents, conflict resolution, bidirectional sync). Rsync-grade engineering. | Keep upload/download manual. Users initiate transfers explicitly. |
| File preview (image/video/document) | Requires media decoders, rendering pipelines, and significant UI work. Out of scope for a transfer-focused client. | Open file externally or link to web viewer. |
| Share management | Complex UI (share list, expiry management, password management). Low value for a personal-use client. | User can share via the 123pan web interface. |
| Offline download (torrent/ed2k) | Requires a download engine integration, seed management, legal considerations. | Out of scope per PROJECT.md. |
| Multi-account support | Requires significant architecture changes (account switching, separate transfer queues, separate DB namespaces). | Single account is the stated scope. |
| Cloud file search | Would need server-side search API or client-side full index. 123pan API does not expose a search endpoint. | Navigate via folders. |

---

## Feature Dependencies

```
F1 (Folder upload button) --> F3 (UI affordance)
                          --> F4 (Error summary after folder upload)
                          --> D1 (Preview dialog)

F5 (Drag-drop visual) --> independent, can be done in parallel

F2 (Progress aggregation) --> optional enhancement after F1 works
                           --> independent of F5

D3 (Folder download) --> independent of folder upload features
D5 (Batch download) --> independent, but shares selection UI changes
```

**Dependency rationale:**
- F1 and F3 are essentially the same work: exposing folder selection in the UI.
- F4 (error summary) depends on F1 being done first, but the per-file retry mechanism already works.
- F5 is a UX polish that can ship independently.
- D3 and D5 are completely independent of the folder upload milestone.

---

## Folder Upload: Detailed Design Decisions

Since the milestone is specifically about folder upload, here is the detailed breakdown of how each aspect should work based on analysis of the existing codebase and common cloud client patterns.

### Trigger Mechanisms

| Trigger | Current State | What Needs to Change |
|---------|--------------|---------------------|
| Drag-drop folder | Already works. `__handleDropEvent` -> `__dropLocalPaths` -> `__prepareLocalUploads` -> `PrepareUploadTask` handles `is_dir()` -> `prepare_folder_upload`. | Nothing. Already implemented. |
| Upload button (file) | Works via `QFileDialog.getOpenFileNames`. | No change needed. |
| Upload button (folder) | Missing. No folder picker. | Add a "Upload Folder" button or make the upload button a split/dropdown with "Upload File" and "Upload Folder" options. |

**Recommendation:** Add a separate "Upload Folder" PushButton next to the existing "Upload" button. This is simpler than a dropdown/split button and more discoverable. The button handler calls `QFileDialog.getExistingDirectory` then feeds the path into the existing `__prepareLocalUploads` method.

### Folder Structure Preservation

The existing `prepare_folder_upload` method in `api.py` already handles this correctly:
1. Walks the local directory tree with `os.walk`
2. Creates remote directories via `_create_directory` (with dedup via `_choose_available_directory_name`)
3. Returns a flat list of `file_targets` with each file's `target_dir_id`

**No changes needed to folder structure logic.**

### Progress Display

| Approach | Pros | Cons | Recommendation |
|----------|------|------|---------------|
| Individual file rows (current) | Already works, no code change, granular control | Cluttered for large folders | Acceptable for MVP |
| Collapsible group row | Clean UI, shows aggregate progress | Complex widget work, custom row type | Defer |
| Summary notification only | Minimal change | No ongoing progress visibility | Insufficient |

**Recommendation for this milestone:** Keep individual file rows (the current behavior). Add a summary notification after all files in the folder upload are queued: "Added 50 upload tasks, created 12 folders." This summary already exists via `__buildUploadSummary`.

### Error Handling

| Scenario | Current Behavior | What to Add |
|----------|-----------------|-------------|
| Single file fails in folder | File shows "Failed" status with retry button. Other files continue. | Nothing -- already works. |
| Directory creation fails | `prepare_folder_upload` raises RuntimeError. Entire folder upload aborts. | This is correct. Partial directory structure with missing subdirectories is worse than a clean failure. |
| Network error during file upload | Per-file retry (up to `retryMaxAttempts`). 429 rate-limit backoff. | Nothing -- already implemented. |
| Folder has 0 files | `prepare_folder_upload` creates the directory structure but returns empty `file_targets`. | Add an InfoBar noting "Folder uploaded (0 files, N directories created)". |

### Edge Cases

| Edge Case | Expected Behavior | Implementation Note |
|-----------|-------------------|-------------------|
| Empty folders | Create directory on remote, no file uploads. Inform user. | `prepare_folder_upload` already handles this. `created_dir_count` will be > 0, `file_targets` will be empty. |
| Folder with symlinks | Skip symlinks to avoid infinite recursion. | `os.walk` does not follow symlinks by default. No change needed. |
| Folder with very deep nesting | Should work, but may be slow for hundreds of nested directories. | API call per directory is the bottleneck. No mitigation needed for MVP. |
| Folder with thousands of files | May take time to walk + stat all files. Show preparation progress. | `PrepareUploadTask` runs in background thread (QThreadPool). UI stays responsive. |
| Drag-drop of mixed files and folders | Upload files to current dir, create folder for each directory. | Already handled in `PrepareUploadTask.run()` which iterates `local_paths` and branches on `is_dir()`. |
| Folder name collision on remote | Auto-rename with `(1)` suffix. | `_choose_available_directory_name` already handles this. |
| File name collision within folder | `duplicate` parameter in upload_request. Currently set to 0 (reject). | Consider setting to 1 (overwrite) or 2 (rename) for folder uploads. Configurable in settings is ideal but not required for MVP. |

---

## MVP Recommendation for This Milestone

The gap is smaller than it appears. Prioritize:

1. **F1 + F3: Add "Upload Folder" button** -- one new PushButton, one `QFileDialog.getExistingDirectory` call, feed into existing `__prepareLocalUploads`. Estimated: ~15 lines of new code.

2. **F5: Drag-drop visual feedback** -- add CSS highlight on the file table viewport during `dragEnterEvent`. Estimated: ~10 lines.

3. **F4: Folder upload error summary** -- after folder upload tasks are queued, if any individual file later fails, the existing per-file retry handles it. Add a completion summary InfoBar. Estimated: ~10 lines.

4. **D1 (optional): Folder upload preview** -- a confirmation dialog showing file count and total size before starting. Estimated: ~30 lines.

**Defer:** F2 (progress aggregation), D2, D3, D4, D5 -- these are enhancements for later milestones.

---

## Sources

- Codebase analysis: api.py, file_interface.py, transfer_interface.py, database.py, setting_interface.py
- PROJECT.md validated requirements and out-of-scope list
- Common cloud client patterns (Google Drive, Dropbox, OneDrive desktop clients) -- folder upload via button is universal table stakes
- 123pan API behavior observed from api.py: uses S3 presigned URLs, multipart upload, rate limiting (429 handling)
