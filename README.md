# Bekoo - ServerSide

[![Giấy phép GitHub](https://img.shields.io/github/license/Chaosql/Bekoo_HuongDichVu)](LICENSE)
[![Người đóng góp](https://img.shields.io/github/contributors/Chaosql/Bekoo_HuongDichVu)](https://github.com/Chaosql/Bekoo_HuongDichVu/graphs/contributors)
[![Kiểm tra và triển khai AWS](https://github.com/Chaosql/Bekoo_HuongDichVu/actions/workflows/deploy-aws.yml/badge.svg)](https://github.com/Chaosql/Bekoo_HuongDichVu/actions/workflows/deploy-aws.yml)

## Mục lục

- [Giới thiệu](#giới-thiệu)
- [Kiến trúc hệ thống](#kiến-trúc-hệ-thống)
- [Yêu cầu chuẩn bị](#yêu-cầu-chuẩn-bị)
- [Cài đặt và triển khai](#cài-đặt-và-triển-khai)
- [Tài liệu API](#tài-liệu-api)
- [Build và kiểm tra](#build-và-kiểm-tra)
- [Đóng góp](#đóng-góp)
- [Liên hệ](#liên-hệ)
- [Giấy phép](#giấy-phép)

## Giới thiệu

**Bekoo** giúp việc đặt lịch khám và quản lý sức khỏe trở nên thuận tiện hơn. Người dùng có thể lựa chọn bác sĩ, chọn khung giờ phù hợp và quản lý lịch hẹn mọi lúc, mọi nơi.

Repository này chứa phần backend của Bekoo, được xây dựng bằng Java 17 và Spring Boot. Hệ thống áp dụng kiến trúc CQRS để tách xử lý ghi và đọc dữ liệu, trao đổi sự kiện thông qua Apache Kafka.

## Kiến trúc hệ thống

| Module / dịch vụ | Vai trò |
|---|---|
| `booking-server-command` | Xử lý thao tác ghi, lưu dữ liệu vào MySQL và phát sự kiện Kafka. |
| `booking-server-query` | Xử lý truy vấn, cập nhật dữ liệu Elasticsearch từ các sự kiện Kafka. |
| `booking-care-document` | Thư viện Java dùng chung, chứa định nghĩa sự kiện, các kiểu dữ liệu phản hồi và hằng số; được đóng gói vào cả hai backend. |
| Apache Kafka | Truyền sự kiện giữa Command và Query. |
| Elasticsearch | Lưu dữ liệu phục vụ tìm kiếm và truy vấn của Query. |
| Redis | Lưu bộ nhớ đệm và dữ liệu tạm thời. |

Command và Query chạy thành hai ứng dụng riêng. Thư viện dùng chung không cần container hoặc cổng riêng.

## Yêu cầu chuẩn bị

Để build dự án:

- Git.
- Java 17. Các module backend đã có Maven Wrapper.
- Python 3 để kiểm tra các script triển khai.

Để triển khai:

- AWS EC2 chạy Amazon Linux 2023, kiến trúc x86_64. Cấu hình demo hiện tại dành cho máy 4 GiB RAM và 2–3 người thử nghiệm đồng thời.
- [Docker Engine](https://docs.docker.com/engine/install/) và [Docker Compose](https://docs.docker.com/compose/install/) phiên bản 2.30 trở lên trên EC2.
- MySQL cài trực tiếp trên EC2; cấu hình hiện tại sử dụng MySQL Community 8.4.
- Các repository Amazon ECR, IAM role và môi trường GitHub Actions theo [hướng dẫn thiết lập AWS](deploy/aws/SETUP-AWS.md).

## Cài đặt và triển khai

### 1. Tải mã nguồn

```bash
git clone https://github.com/Chaosql/Bekoo_HuongDichVu.git
cd Bekoo_HuongDichVu
```

### 2. Cấu hình biến môi trường

Với lần thiết lập đầu tiên, sao chép file mẫu trên máy cá nhân:

```bash
cp deploy/aws/env.aws.example .env.aws
chmod 600 .env.aws
```

Nếu đã có `.env.aws` được cấu hình, hãy giữ file đó, tránh ghi đè bằng file mẫu.

Điền các giá trị bắt buộc, sau đó lưu toàn bộ nội dung file vào GitHub Actions secret `BEKOO_ENV` trong môi trường `production`. Không commit mật khẩu, token hoặc khóa SSH riêng tư vào Git.

Khi database đã có cấu trúc bảng, dùng `DB_DDL_AUTO=validate`. Chỉ dùng `update` cho lần khởi tạo bảng đầu tiên theo hướng dẫn triển khai. Các chức năng email, Cloudinary, VNPay và tạo tài khoản quản trị ban đầu cần được điền các biến tương ứng trước khi thử nghiệm.

### 3. Chuẩn bị AWS và triển khai

Làm theo [SETUP-AWS.md](deploy/aws/SETUP-AWS.md) để cấu hình EC2, MySQL trên máy chủ, mạng Docker, ECR, IAM và các secret, variable của GitHub.

Luồng triển khai:

```text
Push lên main → GitHub Actions build và kiểm tra → Amazon ECR
              → SSH vào EC2 → Docker Compose
              → Kiểm tra trạng thái / khôi phục phiên bản trước khi lỗi
```

Đặt repository variable `AWS_DEPLOY_ENABLED=true` sau khi chuẩn bị xong hạ tầng. Push lên nhánh `main` hoặc chạy thủ công [workflow triển khai](https://github.com/Chaosql/Bekoo_HuongDichVu/actions/workflows/deploy-aws.yml). Command và Query được triển khai với cùng một commit SHA.

EC2 tải các image đã build sẵn. Kafka, Redis và Elasticsearch chạy trong Docker cùng hai backend. Các file phục vụ triển khai được lưu tại `~/bekoo/runtime` trên EC2.

File Compose nằm tại `deploy/aws/compose.yaml`, cần các file biến môi trường đã được tạo, image trên ECR và mạng Docker đã được chuẩn bị. Để khởi chạy đúng cấu hình, thực hiện theo hướng dẫn AWS thay vì chạy `docker compose up -d` tại thư mục gốc repository.

## Tài liệu API

Bản demo hiện tại sử dụng IP công khai của EC2 và hai cổng backend riêng:

| Backend | Địa chỉ gốc | Tài liệu Swagger |
|---|---|---|
| Command | `http://54.255.60.109:8083` | [Swagger Command](http://54.255.60.109:8083/swagger-ui/index.html) |
| Query | `http://54.255.60.109:8084` | [Swagger Query](http://54.255.60.109:8084/swagger-ui/index.html) |

Đặt `SWAGGER_ENABLED=true` trong `BEKOO_ENV` và mở kết nối TCP vào cổng 8083, 8084 trong Security Group của EC2. Khi chuyển sang máy chủ khác, cập nhật IP trong các URL của ứng dụng và quy tắc tường lửa.

Dùng API Command cho thao tác ghi và API Query cho thao tác đọc. Một số API đọc cũ trong Command được đánh dấu `deprecated` nên hiển thị gạch ngang trong Swagger. Với API yêu cầu xác thực, nhập bearer token hợp lệ qua nút **Authorize**.

Các URL demo sử dụng HTTP. Nếu frontend chạy bằng HTTPS, cần backend HTTPS hoặc proxy HTTPS phù hợp để tránh trình duyệt chặn nội dung hỗn hợp (mixed content).

## Build và kiểm tra

Chạy các lệnh sau từ thư mục gốc repository:

```bash
# Build và cài thư viện dùng chung vào kho Maven cục bộ trước.
bash booking-server-query/mvnw -B -f booking-care-document/pom.xml clean install

# Build và chạy các bài kiểm tra backend được chọn.
bash booking-server-command/mvnw -B -f booking-server-command/pom.xml clean verify '-Dtest=*Test'
bash booking-server-query/mvnw -B -f booking-server-query/pom.xml clean verify '-Dtest=*Test'

# Kiểm tra việc chuẩn bị triển khai và xử lý lỗi.
python3 -m unittest discover -s deploy/aws/tests -v
```

Các bài kiểm tra khởi tạo ứng dụng `*ApplicationTests` cần các dịch vụ bên ngoài đang chạy và không nằm trong mẫu chọn test ở trên. Xem [VALIDATION.md](deploy/aws/VALIDATION.md) để biết chi tiết kiểm tra và hướng dẫn AWS để kiểm chứng khi triển khai.

## Đóng góp

Mọi đóng góp đều được hoan nghênh. Bạn có thể tạo [issue](https://github.com/Chaosql/Bekoo_HuongDichVu/issues) để báo lỗi hoặc trao đổi về thay đổi, sau đó gửi pull request kèm mô tả rõ ràng và kết quả kiểm tra liên quan.

## Liên hệ

- GitHub: [Chaosql](https://github.com/Chaosql)
- Trao đổi về dự án và báo lỗi: [GitHub Issues](https://github.com/Chaosql/Bekoo_HuongDichVu/issues)

## Giấy phép

Dự án được cấp phép theo [GNU General Public License v3.0](LICENSE).
