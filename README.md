# Antigravity Multi-Account API Hub & Smart Rotator 🚀

Công cụ quản lý đa tài khoản Google Antigravity, chuyển đổi tài khoản Antigravity thành API chuẩn quốc tế (OpenAI / Anthropic / Direct Responses), tự động xoay tua tài khoản khi chạm ngưỡng Quota hoặc gặp lỗi HTTP 429 mà **HOÀN TOÀN KHÔNG LÀM GIÁN ĐOẠN PHIÊN LÀM VIỆC, KHÔNG MẤT HỘI THOẠI HAY CÔNG VIỆC TRƯỚC ĐÓ**.

---

## 🌟 Tính Năng Nổi Bật

### 1. 🔄 Xoay Tua Tài Khoản Liền Mạch (Zero-Disruption Failover)
* **Bảo toàn ngữ cảnh 100%**: Router ảo hóa toàn bộ lịch sử hội thoại (`messages: [...]`, `systemInstruction`, `contents`, `tool_calls`). Khi chạm quota, toàn bộ ngữ cảnh được chuyển sang tài khoản mới một cách trong suốt.
* **Tự động phòng ngừa (Pre-flight Quota Check)**: Hệ thống theo dõi quota thời gian thực qua Google RPC `retrieveUserQuotaSummary`. Nếu tài khoản hiện tại chạm ngưỡng cảnh báo (&le; 5%), yêu cầu tiếp theo sẽ chủ động định tuyến sang tài khoản dồi dào nhất.
* **Tự động phục hồi lỗi 429 (Reactive Failover)**: Nếu gặp mã `429 (Resource Exhausted / Quota Limit)`, Router sẽ đưa tài khoản vào trạng thái **Cooldown** và lập tức chuyển giao công việc cho tài khoản tiếp theo. Phía ứng dụng client (Codex, Hermes, Claude Code, Cursor) không hề gặp gián đoạn hay phải hỏi lại từ đầu!
* **Stream SSE Buffer**: Hỗ trợ xoay tài khoản mượt mà ngay cả khi đang gọi API ở chế độ Streaming.

---

### 2. 👑 Phân Biệt Tài Khoản Thường & Pro (Google One AI / Pro Tier)
* **Tự động nhận diện Hạng Tài Khoản**: Qua Google RPC `loadCodeAssist`, hệ thống tự động phát hiện `currentTier` và `paidTier` để phân loại tài khoản:
  * 👑 **Tài khoản Pro**: Thẻ viền vàng kim hổ phách (`amber/gold glow`), huy hiệu vương miện `👑 PRO`, hiển thị gói `Google AI Pro`.
  * 🆓 **Tài khoản Thường**: Thẻ xanh hiện đại, huy hiệu `FREE`, hiển thị `Free Tier`.
* **1-Click Chuyển Đổi Hạng**: Nhấp vào nút `PRO` / `FREE` ngay trên thẻ tài khoản hoặc trong modal sửa để chuyển đổi trạng thái tức thì.
* **Bộ Lọc Đa Dạng**: Lọc nhanh theo `Tất cả`, `👑 Pro`, `🆓 Free`, hoặc `🟢 Sẵn sàng`.
* **Thuật Toán Điều Phối Ưu Tiên**: Tùy chọn ưu tiên tài khoản Pro hoặc tài khoản có quota cao nhất khi điều phối request.

---

### 3. ⚡ Tích Hợp Nhanh 1-Click Vào Các Ứng Dụng (Codex, Hermes, Claude...)
Tab **"Tích Hợp Nhanh"** trên Web UI cung cấp thiết lập 1-click tự động:
1. **Hermes Agent (Nous Research)**:
   * 1-Click tự động cập nhật file `AppData\Local\hermes\config.yaml` trỏ về Gateway `http://127.0.0.1:8088`.
   * Tự động tạo bản sao lưu an toàn (`config.yaml.antigravity-hub.bak`).
   * Giữ nguyên 100% memory, skills, tool-calling và conversation database của Hermes!
2. **OpenAI Codex CLI**:
   * 1-Click tạo file phím tắt `Chay_Codex_Voi_Antigravity_API.bat` ngay trên màn hình Desktop.
   * Tự cấu hình `OPENAI_BASE_URL=http://127.0.0.1:8088/v1` và `OPENAI_API_KEY=sk-antigravity`.
3. **Claude Code CLI**:
   * 1-Click tạo file phím tắt `Chay_Claude_Code_API.bat` trên Desktop cấu hình `ANTHROPIC_BASE_URL=http://127.0.0.1:8088`.
4. **Cursor / Windsurf / Cline**:
   * Nút copy nhanh thông số Base URL `http://127.0.0.1:8088/v1` và API Key.

---

### 4. 🎯 Quản Lý Đa Tài Khoản & Hot-Swap IDE
* **Tự động quét & nạp (Auto-Discovery)**: Tự động phát hiện và nạp toàn bộ tài khoản Google từ máy.
* **Đăng nhập Google qua Trình duyệt (Browser OAuth)**: 1-click mở trang Google OAuth trên trình duyệt, tự động bắt mã và thêm tài khoản vào danh sách.
* **Hot-Swap cho Antigravity IDE**: 1-click chuyển đổi tài khoản active trên IDE (`google_accounts.json`, `oauth_creds.json`) mà **không xóa file database `conversation_summaries.db`**, giúp giữ nguyên toàn bộ các tab chat và dự án đang mở trong Antigravity IDE.

---

## 🛠️ Hướng Dẫn Khởi Chạy

### Cách 1: 1-Click Ngoài Desktop (Được Khuyên Dùng)
Nhấp đúp chuột vào file trên màn hình Desktop:
```cmd
Chay_Antigravity_API.bat
```
File này sẽ tự động:
1. Chạy Antigravity API Gateway trên cổng `8088`.
2. Mở sẵn giao diện Web Dashboard trên trình duyệt mặc định: `http://127.0.0.1:8088/`.

---

### Cách 2: Khởi Chạy Từ Thư Mục Dự Án
```cmd
cd "C:\Users\DUCNAM\Desktop\Antigravity-Manager-API"
start.bat
```

---

## 📡 Danh Sách API Endpoints Khả Dụng

| Chuẩn | Endpoint | Phương thức | Dành cho |
|---|---|---|---|
| **Web Dashboard** | `http://127.0.0.1:8088/` | `GET` | Trình duyệt Web |
| **OpenAI Chat** | `http://127.0.0.1:8088/v1/chat/completions` | `POST` | Cursor, Codex, Cline, NextChat |
| **OpenAI Models** | `http://127.0.0.1:8088/v1/models` | `GET` | Danh sách model |
| **Anthropic Messages** | `http://127.0.0.1:8088/v1/messages` | `POST` | Claude Code CLI, Claude SDK |
| **Hermes / Responses** | `http://127.0.0.1:8088/responses` | `POST` | Hermes Agent, Autonomous Agents |

---

## 🚀 Model ID Hỗ Trợ

* **Gemini**: `gemini-3.8-flash-high`, `gemini-3-flash`, `gemini-2.5-pro`, `gemini-3.1-pro-high`
* **Claude**: `claude-sonnet-4-6`, `claude-opus-4-6-thinking` (Thinking Model)
* **Alias tương thích**: `gpt-4o`, `gpt-4o-mini`, `o1`, `claude-3-7-sonnet`
