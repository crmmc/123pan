# Requirements: 123pan 第三方客户端

**Defined:** 2026-04-05
**Core Value:** 文件管理的核心三件事——浏览、上传、下载——必须稳定可靠、操作直观

## v1 Requirements (已完成)

### Folder Upload

- [x] **UPLD-01**: User can select a local folder via button and upload it to the current cloud directory — Phase 1
- [x] **UPLD-02**: User can drag and drop a folder onto the file list area to upload it — Phase 1
- [x] **UPLD-03**: File list area shows visual feedback (highlight border) when folder is dragged over it — Phase 1

### Robustness

- [x] **ROBUST-01**: Directory creation during folder upload is rate-limited to avoid triggering 429 errors — Phase 2
- [x] **ROBUST-02**: Single file preparation failure does not abort the entire folder batch — Phase 2
- [x] **ROBUST-03**: Token expiration during long folder uploads is handled with automatic refresh — Phase 2

## v1.1 Requirements

登录体验重构：拆分"自动登录"为"记住密码"和"保持登录"，新增二维码登录。

### 登录状态管理

- [x] **AUTH-01**: 用户可通过"记住密码"复选框控制密码是否持久化到数据库，勾选时登录成功后存储密码，取消勾选时立即清空数据库中的密码（保留输入框中的值）
- [x] **AUTH-02**: 用户可通过"保持登录"复选框控制 token 是否持久化到数据库，勾选时登录成功后存储 token，默认开启
- [x] **AUTH-03**: 启动时若"保持登录"已开启且数据库中存有 token，优先调用用户信息 API (`api.123pan.cn/b/api/user/info`) 探测 token 有效性，token 有效则直接进入主页面，token 过期才显示登录界面

### 二维码登录

- [ ] **QRC-01**: 登录界面提供二维码登录入口，用户点击后切换到二维码展示界面
- [x] **QRC-02**: 调用 `login.123pan.com/api/user/qr-code/generate` 获取 uniID 和 url，生成二维码图片展示给用户
- [x] **QRC-03**: 约每 1 秒轮询 `login.123pan.com/api/user/qr-code/result?uniID={uniID}` 检查扫码状态，展示等待扫码、已扫码待确认、已确认等状态
- [ ] **QRC-04**: 扫码确认成功后获取 JWT token，与密码登录走相同的后续流程（存储 token/密码、进入主页面）
- [ ] **QRC-05**: 二维码登录支持"保持登录"功能，确认登录后按"保持登录"设置决定是否持久化 token
- [ ] **QRC-06**: 用户可从二维码界面返回密码登录界面

### UI 重构

- [x] **UI-01**: 登录界面将原有的"自动登录"复选框替换为"记住密码"和"保持登录"两个独立复选框
- [ ] **UI-02**: 二维码登录界面包含二维码图片展示区、扫码状态提示、返回按钮

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### UX Enhancement

- **UX-01**: Upload preview dialog showing file count and total size before starting
- **UX-02**: Folder upload progress grouped by source folder in transfer list
- **UX-03**: Resumable folder upload (persist directory structure state for retry)

## Out of Scope

| Feature | Reason |
|---------|--------|
| 密码加密存储 | 用户明确不需要，单子对称加密有心之人总能破解 |
| 多账号二维码登录 | 非核心，当前只有一个账号 |
| 离线下载 | 用户确认不需要 |
| 文件预览 | 非核心功能 |
| 分享管理 | 非核心功能 |
| 同步盘 | 复杂度过高 |
| 多账号支持 | 非核心功能 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| UPLD-01 | Phase 1 | Complete |
| UPLD-02 | Phase 1 | Complete |
| UPLD-03 | Phase 1 | Complete |
| ROBUST-01 | Phase 2 | Complete |
| ROBUST-02 | Phase 2 | Complete |
| ROBUST-03 | Phase 2 | Complete |
| UI-01 | Phase 3 | Complete |
| AUTH-01 | Phase 3 | Complete |
| AUTH-02 | Phase 3 | Complete |
| AUTH-03 | Phase 3 | Complete |
| QRC-01 | Phase 4 | Pending |
| QRC-02 | Phase 4 | Complete |
| QRC-03 | Phase 4 | Complete |
| QRC-04 | Phase 4 | Pending |
| QRC-05 | Phase 4 | Pending |
| QRC-06 | Phase 4 | Pending |
| UI-02 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 6 total, all complete
- v1.1 requirements: 11 total
- Mapped to phases: 11 (Phase 3: 4, Phase 4: 7)
- Unmapped: 0

---
*Requirements defined: 2026-04-05*
*Last updated: 2026-04-08 after v1.1 roadmap creation*
