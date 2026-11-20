# Bekoo - ServerSide

[![Giấy phép GitHub](https://img.shields.io/github/license/Chaosql/Bekoo_HuongDichVu)](https://github.com/Chaosql/Bekoo_HuongDichVu/blob/main/LICENSE)
[![Người đóng góp trên GitHub](https://img.shields.io/github/contributors-anon/Chaosql/Bekoo_HuongDichVu)](https://github.com/Chaosql/Bekoo_HuongDichVu/graphs/contributors)

## Mục lục

- [Giới thiệu](#giới-thiệu)
- [Yêu cầu chuẩn bị 📋](#yêu-cầu-chuẩn-bị-)
- [🔨 Cài đặt](#-cài-đặt)
- [🙌 Đóng góp](#-đóng-góp)
- [Liên hệ](#liên-hệ)
- [📝 Giấy phép](#-giấy-phép)

## Giới thiệu

**Bekoo**: Chăm sóc sức khỏe dễ dàng hơn. Đặt lịch khám với bác sĩ mọi lúc, mọi nơi. Với Bekoo, việc quản lý sức khỏe trở nên thuận tiện hơn bao giờ hết. Bạn chỉ cần chọn bác sĩ mong muốn, chọn khung giờ phù hợp và xác nhận lịch hẹn chỉ với vài thao tác.

### Yêu cầu chuẩn bị 📋

Để cài đặt và chạy dự án, trước tiên bạn cần cài đặt các công cụ bên dưới. Hãy làm theo hướng dẫn cài đặt và chọn đúng hệ điều hành đang sử dụng:

- [Cài đặt Docker](https://docs.docker.com/get-docker/)
- [Cài đặt Docker Compose](https://docs.docker.com/compose/install/)

### 🔨 Cài đặt

Đầu tiên, tải mã nguồn dự án về máy:

```bash
git clone https://github.com/Chaosql/Bekoo_HuongDichVu.git
cd Bekoo_HuongDichVu
```

Tiếp theo, khởi động Docker.

Với phiên bản hiện tại, làm theo [hướng dẫn thiết lập AWS EC2](deploy/aws/SETUP-AWS.md) để chuẩn bị MySQL, mạng Docker, image và các biến môi trường. Khi đã thiết lập xong, trên EC2 có thể khởi động các dịch vụ bằng lệnh:

```bash
cd ~/bekoo/runtime
docker compose --env-file release.env up -d
```

Backend **Command** chạy tại cổng `8083`. Trên máy chủ, bạn có thể mở `http://localhost:8083/swagger-ui/index.html` để xem danh sách API của Command Server.

Backend **Query** chạy tại cổng `8084`. Trên máy chủ, bạn có thể mở `http://localhost:8084/swagger-ui/index.html` để xem danh sách API của Query Server.

Để truy cập bản triển khai từ máy cá nhân:

- [Swagger Command](http://54.255.60.109:8083/swagger-ui/index.html)
- [Swagger Query](http://54.255.60.109:8084/swagger-ui/index.html)

## 🙌 Đóng góp

Nếu muốn đóng góp cho dự án, bạn có thể tạo [issue](https://github.com/Chaosql/Bekoo_HuongDichVu/issues) để trao đổi hoặc gửi pull request.

Mọi đóng góp đều được trân trọng và đánh giá cao — đừng ngần ngại gửi pull request.

## Liên hệ

- Tác giả: [Chaosql](https://github.com/Chaosql)

## 📝 Giấy phép

Dự án được cấp phép theo các điều khoản của giấy phép [GPL V3](https://github.com/Chaosql/Bekoo_HuongDichVu/blob/main/LICENSE).
