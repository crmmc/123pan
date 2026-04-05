# Project Research Summary

**Project:** 123pan Desktop Client - Folder Upload & Drag-Drop Enhancement
**Domain:** Cloud storage desktop client (brownfield, PyQt6)
**Researched:** 2026-04-05
**Confidence:** HIGH

## Executive Summary

This is a brownfield enhancement to an existing PyQt6 cloud storage desktop client. The research reveals a critical finding: the backend for folder upload is already fully implemented. `Pan123.prepare_folder_upload()` in `api.py` handles recursive directory creation and returns a flat file upload plan. The `PrepareUploadTask` in `file_interface.py` already distinguishes between files and directories, and drag-drop already accepts and processes folders end-to-end. The actual implementation gap is remarkably small -- a UI button for folder selection and some defensive hardening.

The recommended approach is to avoid new abstractions, new components, and new dependencies. The existing architecture (QThreadPool for background preparation, pyqtSignal for thread-safe callbacks, flat task queue in TransferInterface) already supports folder upload correctly. The work is primarily a UI change in `file_interface.py` (adding a folder picker button) plus targeted hardening in `api.py` (rate limiting, error recovery, thread safety).

Key risks are not architectural but operational: the existing `Pan123` instance has thread-safety issues when its mutable state is accessed from background threads (Pitfall 4), `prepare_folder_upload` lacks 429 rate-limit handling for batch directory creation (Pitfall 3), and token expiry during long uploads is not handled in the upload path (Pitfall 10). These must be addressed before the folder upload button is exposed to users, since larger folder uploads will amplify these existing latent bugs.

## Key Findings

### Recommended Stack

No new dependencies are required. Everything needed already exists in the codebase.

**Core technologies:**
- **PyQt6 QMimeData + QDropEvent:** Drag-drop is already fully implemented for both files and folders -- no changes needed.
- **PyQt6 QFileDialog.getExistingDirectory:** For the folder picker button; already used in `setting_interface.py` for download path selection.
- **pathlib.Path + os.walk:** Already used in `prepare_folder_upload()` for directory traversal.
- **QThreadPool + QRunnable + pyqtSignal:** Existing background task pattern; no new threading code required.

### Expected Features

**Must have (table stakes):**
- **F1: Folder upload via button** -- every cloud client has this; implementation is ~15 lines using existing `__prepareLocalUploads`.
- **F3: Upload button with file/folder options** -- either a dropdown on the existing button or a separate "Upload Folder" button.
- **F5: Drag-drop visual feedback** -- CSS highlight on the file table viewport during drag-over; ~10 lines.
- **F4: Folder upload error summary** -- completion notification listing any failed files; ~10 lines.

**Should have (differentiators):**
- **D1: Folder upload preview** -- confirmation dialog showing file count and total size before starting; ~30 lines.

**Defer (v2+):**
- F2 (progress aggregation / collapsible group rows), D2 (progress bar in file list), D3 (recursive folder download), D4 (file type icons), D5 (batch select and download).

### Architecture Approach

The architecture already supports folder upload end-to-end. The existing pipeline is: user triggers upload -> `PrepareUploadTask` runs on `QThreadPool` -> calls `Pan123.prepare_folder_upload()` for directories (creates remote dirs, returns flat file list) -> emits signal -> `FileInterface` feeds individual files to `TransferInterface` -> each file uploads via `UploadThread`. No new components needed.

**Major components:**
1. **FileInterface** -- adds folder picker button; drag-drop already works.
2. **PrepareUploadTask (existing)** -- background preparation, already handles directories.
3. **Pan123.prepare_folder_upload (existing)** -- recursive directory creation + file plan; needs hardening for rate limits and error recovery.
4. **TransferInterface (existing)** -- manages individual file uploads; no changes needed.

### Critical Pitfalls

1. **Pan123 thread-safety violation** -- shared instance state (`file_page`, `parent_file_id`) mutated from background threads without locks. Fix: do not touch Pan123 instance state from threads; extract auth info and call API directly.
2. **API rate limiting (429) during batch directory creation** -- `prepare_folder_upload` makes sequential POST calls with no backoff. Fix: add inter-request delay (100-200ms) and exponential backoff on 429.
3. **Token expiry during long folder uploads** -- upload path lacks the re-login logic that the file-listing path has. Fix: check for code 2 response in `upload_file_stream` and trigger re-login.
4. **Blocking UI with large folder traversal** -- `os.walk` + sequential mkdir calls are coupled in one method. Fix: separate local traversal from remote creation; add file count limit with user warning.
5. **Single failure aborts mixed drag-drop batch** -- one permission-denied error kills all items in the drop. Fix: per-item try/except in `PrepareUploadTask`.

## Implications for Roadmap

### Phase 1: UI Entry Point -- Folder Upload Button
**Rationale:** This is the smallest, highest-value change. It can be tested immediately because the entire backend pipeline already exists.
**Delivers:** Users can select and upload a folder via a button in the toolbar.
**Addresses:** F1, F3 from FEATURES.md.
**Avoids:** Anti-Pattern 1 (blocking UI) -- reuses existing QThreadPool pattern.
**Files:** `src/app/view/file_interface.py` only.

### Phase 2: Hardening -- Rate Limiting, Thread Safety, Error Recovery
**Rationale:** Before folder upload gets real-world use, the latent bugs in `api.py` must be fixed. These are existing issues that large folder uploads will trigger.
**Delivers:** Robust folder upload that handles 429s, token expiry, partial failures, and concurrent access safely.
**Addresses:** Pitfalls 2, 3, 4, 10, 11, 14 from PITFALLS.md.
**Uses:** Existing `Retry` adapter pattern from `requests` session (extend for 429).
**Files:** `src/app/common/api.py` primarily.

### Phase 3: UX Polish -- Visual Feedback, Progress, Summaries
**Rationale:** After core functionality is solid, add the user-facing polish that separates a working feature from a good experience.
**Delivers:** Drag-drop visual feedback, folder preparation progress signal, upload completion summary, optional preview dialog.
**Addresses:** F4, F5, D1 from FEATURES.md; Pitfalls 7, 6 from PITFALLS.md.
**Files:** `src/app/view/file_interface.py`, `src/app/view/transfer_interface.py`.

### Phase Ordering Rationale

- Phase 1 comes first because it has zero dependencies and proves the existing backend works end-to-end. It is the fastest path to a testable feature.
- Phase 2 follows because hardening is needed before real-world use but is not required for initial testing with small folders. Fixing thread safety and rate limiting in Phase 2 means Phase 1 can ship as a "small folders only" capability while Phase 2 removes that limitation.
- Phase 3 is last because it is purely cosmetic and can be deferred without blocking functionality.
- This ordering minimizes risk: each phase touches a minimal set of files, and no phase depends on architectural changes from another.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2:** Thread safety fix may require careful analysis of all call sites that mutate Pan123 state from background threads. The scope of the fix depends on how many methods share this pattern.

Phases with standard patterns (skip research-phase):
- **Phase 1:** Follows the exact same pattern as the existing upload button; `QFileDialog.getExistingDirectory` is a one-liner already used in the codebase.
- **Phase 3:** Standard PyQt6 stylesheet and signal patterns; well-documented.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | No new libraries needed; all APIs verified by runtime checks and codebase analysis. |
| Features | HIGH | Feature list derived from direct codebase analysis; gaps are clearly identified and small. |
| Architecture | HIGH | Data flow traced through actual code; the "already works" finding is confirmed at multiple levels. |
| Pitfalls | HIGH | Pitfalls identified by reading actual code; thread-safety and rate-limiting issues are verifiable. |

**Overall confidence:** HIGH

### Gaps to Address

- **Thread-safety scope:** The full scope of shared Pan123 state mutation from background threads is not fully mapped. During Phase 2 planning, audit all QRunnable subclasses that access `self.pan` to understand the complete fix surface.
- **123pan API rate limit thresholds:** The exact rate limits for directory creation endpoints are unknown. During Phase 2, empirically test with 50+ directories to calibrate delay values.
- **Nested duplicate name handling:** `_choose_available_directory_name` handles root-level collisions but nested collision behavior depends on the 123pan server response. Verify during Phase 2 testing.

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis of `api.py`, `file_interface.py`, `transfer_interface.py`, `database.py`, `setting_interface.py`
- PyQt6 6.10.2 runtime verification on this machine (QMimeData, QUrl, QFileDialog confirmed)
- Python stdlib documentation (`os.walk`, `pathlib.Path`)

### Secondary (MEDIUM confidence)
- 123pan API behavior inferred from existing implementation (429 handling, token expiry patterns)
- Common cloud client UX patterns (Google Drive, Dropbox, OneDrive) -- folder upload button is universal

---
*Research completed: 2026-04-05*
*Ready for roadmap: yes*
