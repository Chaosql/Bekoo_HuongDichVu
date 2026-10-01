# Bekoo_HuongDichVu

Backend Bekoo gồm ba module: thư viện sự kiện dùng chung, Command (MySQL)
và Query (Elasticsearch). Source gốc: https://github.com/RoanDevBackend/Bekoo;
giữ nguyên LICENSE. Hướng dẫn gốc nằm trong README-BEKOO.md.

## Cấu hình và chạy local

1. Copy `.env.example` thành `.env` và điền các giá trị riêng.
2. Điền MYSQL_ROOT_PASSWORD, DB_PASSWORD, REDIS_PASSWORD, ELASTIC_PASSWORD
   và JWT_SECRET. Khi dùng MySQL local với user root, hai mật khẩu MySQL phải
   giống nhau. JWT_SECRET là Base64 của ít nhất 32 byte ngẫu nhiên
   (có thể tạo bằng `openssl rand -base64 32`) và dùng chung cho hai service.
3. Điền Cloudinary, SMTP, VNPay và API_KEY nếu sử dụng các tính năng tương ứng.
4. Để ADMIN_EMAIL/ADMIN_PASSWORD trống nếu không cần tạo admin lúc khởi động.
   Nếu tạo admin, điền cả email, password và các trường ADMIN_* về hồ sơ;
   ADMIN_DOB dùng định dạng YYYY-MM-DD. Không có mật khẩu admin mặc định.

Chạy tại thư mục gốc của repo bằng Docker Compose v2:

```bash
docker compose config --quiet
docker compose up -d --build
```

Command: http://localhost:8083; Query: http://localhost:8084.
Compose build source trong repo này, không chạy image backend cũ từ Docker Hub.
MySQL, Redis, Kafka, Elasticsearch và AI chỉ truy cập qua mạng Docker nội bộ.
Các compose trong từng module chuyển tới stack gốc qua `include`;
chức năng này cần Docker Compose 2.20 trở lên.

Spring Boot chạy trực tiếp không tự đọc .env; phải truyền environment variables
cho từng JVM, đặc biệt SERVER_PORT và SPRING_URL riêng cho Command/Query.
Mật khẩu của MySQL/Elasticsearch trong volume đã tồn tại cần đổi trên dịch vụ,
không tự thay đổi khi sửa .env.

Không commit .env. Các credential từng nằm trong source cũ cần được revoke/rotate;
xóa khỏi source mới không làm credential cũ trở nên an toàn.

## Build

Yêu cầu JDK 17 và Maven (hoặc Maven Wrapper):

```bash
./booking-server-query/mvnw -f booking-care-document/pom.xml clean install
./booking-server-command/mvnw -f booking-server-command/pom.xml clean package -DskipTests
./booking-server-query/mvnw -f booking-server-query/pom.xml clean package -DskipTests
```

Các test context gốc cần các dịch vụ ngoài và cấu hình runtime.
Unit test về credential có thể chạy riêng bằng `-Dtest=JwtEnvironmentTest`
cho Query, và `-Dtest=JwtEnvironmentTest,ExternalCredentialsTest,AdminEnvironmentTest`
cho Command.

Tài liệu AWS tham khảo: [CHIIKAIWA-BE-AWS-DEPLOYMENT-GUIDE.md](CHIIKAIWA-BE-AWS-DEPLOYMENT-GUIDE.md).
Repo chưa có pipeline AWS hoặc tài nguyên AWS được triển khai.
