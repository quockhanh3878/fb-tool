# AGENTS

Hợp đồng vận hành cho mọi coding agent trong repo này nằm trọn ở **[`CLAUDE.md`](CLAUDE.md)**.

File này chỉ là con trỏ, cố ý không chứa nội dung, để không phải đồng bộ hai bản.

**Trước khi làm bất cứ việc gì trong repo: đọc `CLAUDE.md` từ đầu đến cuối.**

Năm ràng buộc nghiêm ngặt nhất, nhắc lại ở đây để không ai lỡ tay:

1. **Không đọc, in, copy hay commit** `commhunter/data/`, `chrome-debug-profile/`, `.env`, `commhunter/configs/*.yaml` — đó là session cookie Facebook và API key của khách (CLAUDE.md §7, §14).
2. **Mọi hành vi ghi lên Facebook thật cần được đồng ý rõ trong cuộc hội thoại hiện tại**; test chỉ trên nick phụ qua Chrome CDP `9222` và phải dọn sạch sau khi xong (§8).
3. **`ai-comment-bot-main/`, `fbn-main/`, `openclaw-skills-main/` chỉ để đọc tham khảo** — không sửa, không import vào đường chạy thật (§1).
4. **Chỉ ghi trạng thái `Xong` trong `docs/plans/DELIVERY_STATUS.md` khi có mã chạy được VÀ có test chứng minh** (§4).
5. **Cấm emoji tuyệt đối** ở mọi nơi, trừ giao diện người dùng thật (thẻ Telegram, dashboard). Đánh dấu trạng thái bằng chữ: `Xong` / `Chờ` / `[OK]` / `[LỖI]` (§10).
