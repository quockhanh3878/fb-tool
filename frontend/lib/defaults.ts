// plan: docs/plans/phase2_dashboard_detail.md
/**
 * Nội dung bài đăng và bình luận mẫu mặc định cho khách hàng Nyatymita.
 */

export const DEFAULT_POST_TITLE =
  "TIỆM CƠM ĐẦU TIÊN MỞ WEBSITE WRITING COMMISSION CHUYÊN NGHIỆP";

export const DEFAULT_POST_CONTENT = `Dịch vụ chấp bút của Nyatymita là dịch vụ chuyên nghiệp nyatymita.com đầu tiên trong giới writing commission thực hiện website riêng tư dành cho việc đặt chấp bút. Khách hàng sẽ có đủ sự riêng tư và thoải mái khi nhận được bản thảo được trình bày chỉn chu trên trình duyệt Chrome và Safari, nhận thông báo cập nhật đơn hàng nhanh chóng và tiện lợi, cùng nhiều ưu đãi dành riêng cho khách hàng đặt writing comm qua web.


Độ bảo mật cao và luôn tạo sự thoải mái cho khách hàng là tiêu chí hàng đầu của nyatymita.com. Khi đăng ký tài khoản và đặt hàng qua web, bạn có thể nhận được các ưu đãi sau đây:


❤ Khuyến mãi khách mới:

 Với khách lần đầu đặt dịch vụ của t qua web sẽ được tặng FREE 500w

❤ Mốc son vạn dặm:

Có 2 ưu đãi mốc son dành cho đơn thường và tính theo số từ long fic, quà tặng có giá trị tăng tiến theo quá trình tích luỹ đơn hàng và số từ. Chi tiết vui lòng xem tại website.

❤ Ưu đãi thăng hạng:

Khi đăng ký tài khoản và đặt đơn qua web, khách hàng sẽ được tích luỹ điểm để thăng hạng. Mỗi hạng sẽ được cung cấp ưu đãi theo quý/event/đơn hàng khác nhau. 

❤ Gacha mỗi ngày, vận may tăng tiến:

Checkin daily để nhận ticket quay gacha với nhiều phần thưởng tặng từ, giảm giá và oneshot giá trị cao.

❤ Event collab Nyatymita’s Writing Commission x Hải Lam Audio:

Đặt gói combo fiction 5kw trở lên kèm gói chuyển thể audio cho OPT của bạn để được giảm đến 5%.

❤ Coupon Meow Paws Circle:

Chọn 1 trong 6 gian hàng circle của Meow Paws Circle để nhận coupon tặng 500w miễn phí.

❤ Khách hàng đặt lại lần thứ 2 trở đi: 

Tặng 500w cho đơn hàng thứ 2; tặng 1000w cho đơn hàng thứ 3; tặng 1500w cho đơn hàng thứ 4; giảm 5% cho đơn hàng thứ 5 và cố định giảm 5% cho các đơn hàng kế tiếp.

Cùng nhiều ưu đãi hấp dẫn khách cho khách mới, khách quay lại đặt lần nữa, khách đặt qua website…

Dịch vụ Chấp bút của Nyatymita là tiệm cơm chuyên nhận long fic đa dạng thể loại và đề tài, với ngòi bút linh hoạt và dịch vụ khách hàng chất lượng sẽ mang lại trải nghiệm tốt nhất có thể cho khách hàng.

Vui lòng đọc samples SFW và NSFW tại website nyatymita.com.


Lưu ý: Không khuyến khích, cổ suý người dưới 18 tuổi tham khảo nội dung comm NSFW.


Không nhận đơn NSFW đối với người dưới 18 tuổi và chưa có khả năng tự chủ tài chính.`.trim();

export const DEFAULT_COMMENT_TEXT = `Chào bạn, 

Mình chuyên nhận long fic, shortfic, đơn n5fw, build plot/OC đa dạng thể loại và đề tài, bạn có thể tham khảo danh sách comm đã hoàn thành làm samples, thống kê theo thể loại được đăng tải tại nyatymita.wordpress.com. Xem các thông tin khuyến mãi và bảng giá tại: FB Xưởng Chữ Nyatymita hoặc nyatymita.com nha.

Để đọc các bản thảo thể loại NSFW, vui lòng nhắn tin cho Xưởng Chữ Nyatymita để được tư vấn kỹ hơn.

Không cổ xuý, chia sẻ bản thảo NSFW cho người dưới tuổi trưởng thành. 

Samples được đăng tải tại: nyatymita.com.`.trim();

/**
 * Cấu hình tần suất đăng bài và đẩy cmt mặc định cho ứng dụng:
 * - Đăng bài vào các nhóm: 2 tuần / lần (14 ngày).
 * - Tự động cmt đẩy bài dưới link đã đăng: 4 lần / ngày vào các khung giờ 10h, 17h, 19h, 21h.
 */
export const DEFAULT_REPEAT_INTERVAL_DAYS = 14;
export const DEFAULT_AUTO_BUMP = true;
export const DEFAULT_BUMP_HOURS = [10, 17, 19, 21];
