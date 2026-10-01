# Luồng triển khai AWS theo dự án Chiikaiwa-BE

## 1. Mục đích

Tài liệu này mô tả cách dự án `Chiikaiwa-BE` được build và triển khai lên AWS, đồng thời cung cấp một khuôn mẫu để các dự án backend Java/Spring Boot khác có thể áp dụng.

Luồng tổng quát:

```text
Developer push code lên nhánh main
                 |
                 v
          GitHub Actions
       - Build JAR bằng Maven
       - Build Docker runtime image
                 |
                 v
          Amazon ECR
       - Lưu image theo commit SHA
       - Cập nhật image latest
                 |
                 v
         SSH vào Amazon EC2
       - Tạo/cập nhật file .env
       - Đăng nhập ECR
       - Pull image mới
       - Dừng container cũ
       - Chạy container mới
                 |
                 v
          Backend hoạt động
       - Kết nối Amazon RDS
       - Kết nối Redis trên EC2
```

## 2. Kiến trúc triển khai của Chiikaiwa-BE

Các thành phần chính:

| Thành phần | Vai trò |
|---|---|
| GitHub | Lưu source code và kích hoạt CI/CD |
| GitHub Actions | Build JAR, build Docker image, push ECR và điều khiển deploy |
| Amazon ECR | Lưu Docker image của backend |
| Amazon EC2 | Chạy container backend và Redis |
| Amazon RDS PostgreSQL | Lưu dữ liệu nghiệp vụ |
| Redis | Cache, rate limit, trạng thái online và dữ liệu tạm |
| GitHub Secrets | Lưu thông tin AWS, SSH và secret ứng dụng |

Chiikaiwa-BE không build source trên EC2. Việc build được thực hiện trên GitHub Actions; EC2 chỉ pull image và chạy container. Cách này giảm tải CPU/RAM cho máy chủ và làm cho kết quả build nhất quán hơn.

## 3. Các file tham gia vào quá trình deploy

| File | Chức năng |
|---|---|
| `.github/workflows/deploy-aws.yml` | Định nghĩa toàn bộ pipeline CI/CD |
| `aws.Dockerfile` | Tạo runtime image từ JAR đã được build |
| `src/main/resources/application-aws.properties` | Cấu hình Spring Boot cho môi trường AWS |
| `.env.example` | Mẫu các biến môi trường ứng dụng cần |
| `.dockerignore` | Loại file không cần thiết khỏi Docker build context |

Ngoài ra, `Dockerfile` và `docker-compose.yml` hiện hữu chủ yếu phục vụ build hoặc chạy ở môi trường khác. Pipeline AWS sử dụng riêng `aws.Dockerfile`.

## 4. Điều kiện kích hoạt pipeline

Workflow được chạy khi:

- Có commit được push lên nhánh `main`.
- Người vận hành chạy thủ công bằng `workflow_dispatch` trên GitHub Actions.

Workflow sử dụng `concurrency` để tránh hai lần deploy cùng nhánh chạy đồng thời. Khi có bản mới hơn, workflow cũ đang chạy có thể bị hủy.

```yaml
on:
  push:
    branches: [main]
  workflow_dispatch:

concurrency:
  group: deploy-${{ github.ref }}
  cancel-in-progress: true
```

## 5. Luồng build trên GitHub Actions

### Bước 1: Checkout source code

Runner tải đúng phiên bản source tương ứng với commit kích hoạt workflow.

```yaml
- name: Checkout code
  uses: actions/checkout@<pinned-commit>
```

Các GitHub Action nên được pin bằng commit SHA thay vì chỉ dùng tag để hạn chế rủi ro supply chain.

### Bước 2: Cài JDK và cache Maven

Chiikaiwa-BE sử dụng Java 17 và Temurin JDK. Maven dependencies được cache để giảm thời gian build ở các lần sau.

```yaml
- name: Set up JDK 17
  uses: actions/setup-java@<pinned-commit>
  with:
    java-version: "17"
    distribution: temurin
    cache: maven
```

### Bước 3: Build JAR

GitHub runner dùng Maven Wrapper của dự án để tạo JAR:

```bash
chmod +x mvnw
./mvnw clean package -DskipTests -B
```

Trong pipeline hiện tại, test được bỏ qua bằng `-DskipTests`. Dự án học theo nên có một job test riêng chạy trước job deploy và chỉ cho phép deploy khi test thành công.

Kết quả của bước này là file JAR trong thư mục `target/`.

### Bước 4: Xác thực với AWS

Workflow lấy AWS credentials từ GitHub Secrets và cấu hình region:

```yaml
- name: Configure AWS credentials
  uses: aws-actions/configure-aws-credentials@<pinned-commit>
  with:
    aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
    aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
    aws-region: ap-southeast-1
```

Luồng Chiikaiwa-BE hiện dùng access key. Với dự án mới, nên ưu tiên GitHub OIDC và IAM Role để không phải lưu AWS access key dài hạn trong GitHub.

### Bước 5: Đăng nhập Amazon ECR

`amazon-ecr-login` trả về địa chỉ ECR registry để các bước sau build và push image.

```yaml
- name: Login to Amazon ECR
  id: login-ecr
  uses: aws-actions/amazon-ecr-login@<pinned-commit>
```

### Bước 6: Build runtime image

`aws.Dockerfile` không chạy Maven. Nó chỉ copy JAR được tạo ở bước trước vào một Java runtime image:

```dockerfile
FROM eclipse-temurin:17-jre-alpine

WORKDIR /app

RUN addgroup -S spring && adduser -S spring -G spring
USER spring:spring

COPY target/<application>.jar app.jar

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "-Dspring.profiles.active=${SPRING_PROFILES_ACTIVE:aws}", "app.jar"]
```

Runtime image của Chiikaiwa-BE còn cấu hình heap và G1 Garbage Collector phù hợp với tài nguyên EC2. Khi áp dụng cho dự án khác, không sao chép nguyên giá trị `-Xms` và `-Xmx`; phải điều chỉnh theo RAM của máy và số container cùng chạy.

Image được gắn hai tag:

```text
<ECR registry>/<repository>:<git commit SHA>
<ECR registry>/<repository>:latest
```

Tag SHA dùng để truy vết và rollback; `latest` đại diện cho bản mới nhất.

### Bước 7: Chuẩn bị dữ liệu đặc biệt

Nếu secret là JSON nhiều dòng, như Firebase service account, pipeline mã hóa Base64 trước khi chuyển qua SSH. Trên EC2, dữ liệu được giải mã và ghi vào biến môi trường ở dạng một dòng.

Không in secret ra log và không commit file credential vào repository.

## 6. Luồng deploy trên EC2

GitHub Actions dùng SSH key trong GitHub Secrets để kết nối EC2:

```yaml
- name: Deploy to EC2
  uses: appleboy/ssh-action@<pinned-commit>
  with:
    host: ${{ secrets.EC2_HOST }}
    username: ec2-user
    key: ${{ secrets.EC2_SSH_KEY }}
```

Script trên EC2 thực hiện tuần tự các bước sau.

### Bước 1: Dừng ngay khi có lỗi

```bash
set -e
```

Một lệnh lỗi sẽ làm deployment thất bại thay vì tiếp tục với trạng thái không xác định.

### Bước 2: Tạo file môi trường

Pipeline sinh file riêng trên EC2, ví dụ:

```text
/home/ec2-user/<project>/.env
```

File chứa địa chỉ database, thông tin Redis và các secret ứng dụng. File `.env`:

- Không nằm trong Git repository.
- Chỉ user vận hành được quyền đọc.
- Không được in nội dung ra log.
- Nên được tạo với permission `600`.

Ví dụ nhóm biến, không phải giá trị thật:

```dotenv
SPRING_PROFILES_ACTIVE=aws
DB_HOST=<rds-endpoint>
DB_PORT=5432
DB_NAME=<database-name>
DB_USERNAME=<database-user>
DB_PASSWORD=<database-password>
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=<redis-password>
JWT_SECRET=<jwt-secret>
```

### Bước 3: Đăng nhập ECR trên EC2

EC2 lấy Docker login token từ AWS CLI:

```bash
aws ecr get-login-password --region ap-southeast-1 \
  | docker login --username AWS --password-stdin <ECR registry>
```

EC2 nên dùng IAM Instance Role có quyền pull ECR thay vì nhận access key từ GitHub Actions.

Quyền tối thiểu thường gồm:

- `ecr:GetAuthorizationToken`
- `ecr:BatchCheckLayerAvailability`
- `ecr:GetDownloadUrlForLayer`
- `ecr:BatchGetImage`

### Bước 4: Pull image mới

```bash
docker pull <ECR registry>/<repository>:latest
```

Pipeline gốc của Chiikaiwa-BE pull `latest`. Dự án mới nên truyền `github.sha` sang EC2 và chạy đúng tag SHA để bảo đảm image được deploy chính là image vừa build.

### Bước 5: Thay container

Container cũ được dừng và xóa trước khi chạy container mới:

```bash
docker stop <container-name> 2>/dev/null || true
docker rm <container-name> 2>/dev/null || true

docker run -d \
  --name <container-name> \
  --restart unless-stopped \
  --network host \
  --env-file /home/ec2-user/<project>/.env \
  <ECR registry>/<repository>:<image-tag>
```

Chiikaiwa-BE dùng `--network host`, vì vậy ứng dụng có thể truy cập Redis trên EC2 bằng `localhost`. Nếu dự án có nhiều container phụ thuộc nhau, nên cân nhắc Docker bridge network và dùng tên service thay cho `localhost`.

Cách dừng rồi chạy lại container tạo ra một khoảng downtime ngắn. Nếu cần zero-downtime, phải mở rộng sang hai container, reverse proxy/load balancer và health check trước khi chuyển traffic.

### Bước 6: Dọn image cũ

```bash
docker image prune -f
```

Chỉ dọn dangling image. Không xóa image đang được container sử dụng hoặc image rollback gần nhất.

### Bước 7: Kiểm tra trạng thái

Pipeline gốc kiểm tra container bằng:

```bash
docker ps --filter name=<container-name>
```

Dự án mới nên kiểm tra thêm health endpoint, ví dụ:

```bash
curl --fail --retry 12 --retry-delay 5 \
  http://127.0.0.1:8080/actuator/health
```

Chỉ công nhận deployment thành công khi endpoint trả về trạng thái healthy.

## 7. Cấu hình ứng dụng cho AWS

Chiikaiwa-BE kích hoạt Spring profile `aws`. File cấu hình AWS ánh xạ environment variables sang Spring properties:

```properties
spring.datasource.url=jdbc:postgresql://${DB_HOST}:${DB_PORT:5432}/${DB_NAME}
spring.datasource.username=${DB_USERNAME}
spring.datasource.password=${DB_PASSWORD}

spring.data.redis.host=${REDIS_HOST:localhost}
spring.data.redis.port=${REDIS_PORT:6379}
spring.data.redis.password=${REDIS_PASSWORD:}
```

Nguyên tắc để dự án khác áp dụng:

1. Giá trị không nhạy cảm có thể có default hợp lý.
2. Password, token và private key không có default production.
3. Tất cả endpoint môi trường phải truyền từ bên ngoài.
4. Profile AWS phải giảm log SQL và log debug.
5. Không đặt credential thật trong `application-aws.properties` hoặc `application-aws.yml`.

## 8. GitHub Secrets cần có

Pipeline Chiikaiwa-BE sử dụng các nhóm secret sau.

### AWS và EC2

```text
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
EC2_HOST
EC2_SSH_KEY
```

### Database

```text
DB_HOST
DB_PASSWORD
```

Tên database và database user hiện được đặt trực tiếp trong script deploy. Dự án mới nên đưa cả hai thành biến cấu hình:

```text
DB_NAME
DB_USERNAME
```

### Secret ứng dụng

```text
JWT_SECRET
FIREBASE_CREDENTIALS
CLOUD_NAME
CLOUD_API_KEY
CLOUD_API_SECRET
BREVO_NAME
BREVO_SENDER_EMAIL
BREVO_API_KEY
```

Mỗi dự án cần lập danh sách riêng dựa trên toàn bộ `${...}` trong file cấu hình và `@Value`/`ConfigurationProperties` trong source.

## 9. Yêu cầu chuẩn bị trên AWS

### Amazon ECR

- Tạo repository trước lần deploy đầu tiên.
- Bật image scanning nếu phù hợp.
- Thiết lập lifecycle policy để xóa image quá cũ nhưng giữ đủ phiên bản rollback.

### Amazon EC2

- Cài Docker và AWS CLI.
- Gắn IAM Instance Role có quyền pull ECR.
- Tạo thư mục ứng dụng.
- Bật Docker tự khởi động cùng hệ điều hành.
- Bảo đảm disk đủ cho image và log.
- Đồng bộ thời gian hệ thống.

### Amazon RDS

- Đặt RDS và EC2 trong VPC có kết nối nội bộ.
- Security Group của RDS chỉ nhận kết nối từ Security Group của EC2.
- Không public database nếu không có yêu cầu đặc biệt.
- Bật backup tự động và xác định retention phù hợp.

### Security Group của EC2

- SSH chỉ mở từ nguồn quản trị hoặc cơ chế CI/CD được kiểm soát.
- Chỉ public cổng ứng dụng thực sự cần thiết.
- Không public Redis hoặc database.
- Với production, ưu tiên đưa ứng dụng sau ALB hoặc reverse proxy HTTPS.

## 10. Khuôn mẫu để dự án khác áp dụng

Mỗi dự án mới cần thay các giá trị sau:

| Giá trị | Ví dụ Chiikaiwa-BE | Cần thay thành |
|---|---|---|
| AWS region | `ap-southeast-1` | Region dự án |
| ECR repository | `chiikaiwa-be` | Tên repository mới |
| JAR path | JAR trong `target/` | JAR thực tế của dự án |
| Container name | `chiikaiwa-be` | Tên container mới |
| EC2 directory | `/home/ec2-user/chiikaiwa` | Thư mục dự án mới |
| Application port | `8080` | Cổng ứng dụng mới |
| Spring profile | `aws` | Profile môi trường mới |
| Environment variables | DB, Redis, JWT, Firebase... | Dependency thực tế |
| Health endpoint | Chưa kiểm tra đầy đủ | Endpoint health dự án |

Không sao chép nguyên pipeline nếu dự án có:

- Nhiều module cần build theo thứ tự.
- Nhiều application/container.
- Kafka, Elasticsearch hoặc message broker.
- Database migration riêng.
- Worker hoặc scheduled job.
- Yêu cầu zero-downtime.

Trong các trường hợp đó, vẫn giữ xương sống `build → ECR → EC2`, nhưng mở rộng bước build, thứ tự khởi động, health check và rollback.

## 11. Quy trình rollback khuyến nghị

Do image đã được tag bằng commit SHA, rollback có thể thực hiện bằng cách chạy lại SHA trước đó:

```bash
docker pull <ECR registry>/<repository>:<previous-sha>
docker stop <container-name>
docker rm <container-name>
docker run -d \
  --name <container-name> \
  --restart unless-stopped \
  --network host \
  --env-file /home/ec2-user/<project>/.env \
  <ECR registry>/<repository>:<previous-sha>
```

Pipeline hoàn chỉnh nên:

1. Ghi nhận SHA đang chạy trước khi deploy.
2. Khởi động phiên bản mới.
3. Chờ health check.
4. Nếu health check thất bại, tự động chạy lại SHA trước.
5. Giữ log của phiên bản lỗi để điều tra.

Rollback application không đồng nghĩa rollback database. Nếu dự án dùng Flyway hoặc Liquibase, migration phải tương thích ngược hoặc có kế hoạch rollback riêng.

## 12. Checklist trước khi đưa một dự án mới lên AWS

### Source và build

- [ ] Dự án build thành công trên môi trường sạch.
- [ ] Test chạy trước deployment.
- [ ] JAR name/path xác định rõ.
- [ ] Runtime Dockerfile không chứa tool build không cần thiết.
- [ ] Container chạy bằng non-root user.

### Configuration và security

- [ ] Không có secret hard-code trong source.
- [ ] Không commit `.env` hoặc private key.
- [ ] GitHub Secrets đã khai báo đủ.
- [ ] IAM tuân theo least privilege.
- [ ] Database và Redis không public.
- [ ] Credential từng bị commit đã được rotate.

### AWS

- [ ] ECR repository đã tồn tại.
- [ ] EC2 đã cài Docker và AWS CLI.
- [ ] EC2 có IAM Role để pull ECR.
- [ ] RDS đã tạo database/user.
- [ ] Security Group đã cấu hình.
- [ ] Backup và disk monitoring đã bật.

### Deployment

- [ ] Có tag image theo commit SHA.
- [ ] Có health check sau khi start.
- [ ] Có smoke test cho API chính.
- [ ] Có phương án rollback.
- [ ] Có giới hạn dung lượng log và image.
- [ ] Có cảnh báo khi workflow thất bại.

## 13. Các cải tiến nên áp dụng so với pipeline gốc

Luồng Chiikaiwa-BE là nền tảng đơn giản và dễ học theo. Khi chuẩn hóa cho dự án khác, nên bổ sung:

1. Chạy test thay vì chỉ `-DskipTests`.
2. Dùng GitHub OIDC thay cho AWS access key dài hạn.
3. Dùng IAM Instance Role để EC2 pull ECR.
4. Deploy chính xác tag commit SHA thay vì chạy `latest`.
5. Kiểm tra `/actuator/health` sau khi khởi động.
6. Tự động rollback khi health check thất bại.
7. Dùng file permission `600` cho `.env`.
8. Không truyền AWS credentials xuống EC2 qua SSH.
9. Đặt lifecycle policy cho ECR và log rotation cho Docker.
10. Dùng HTTPS qua ALB hoặc reverse proxy cho production.

## 14. Tóm tắt

Điểm cốt lõi của cách triển khai Chiikaiwa-BE là tách build khỏi máy chủ:

```text
GitHub Actions chịu trách nhiệm build và đóng gói.
Amazon ECR chịu trách nhiệm lưu version của image.
Amazon EC2 chỉ chịu trách nhiệm pull và chạy image.
Amazon RDS chịu trách nhiệm lưu database production.
GitHub Secrets cung cấp cấu hình nhạy cảm tại thời điểm deploy.
```

Các dự án khác nên giữ nguyên mô hình trách nhiệm này, nhưng phải điều chỉnh số lượng module, dependency, tài nguyên EC2, biến môi trường, health check và chiến lược rollback theo kiến trúc thực tế của mình.
