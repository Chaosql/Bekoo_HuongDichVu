# Setup AWS cho Bekoo: MySQL và Redis trên EC2

Luồng giữ cách triển khai Chiikaiwa-BE:
push main → GitHub Actions build JAR → runtime image → ECR → SSH EC2 → pull/restart.
Bekoo có hai image và nhiều middleware, nên sử dụng Docker Compose trên EC2.

## 1. Tạo EC2 dành cho Bekoo

- Region mặc định: ap-southeast-1.
- AMI: Amazon Linux 2023, CPU x86_64 (image ứng dụng là linux/amd64).
- Dự kiến khoảng 8 GB RAM cho staging rồi đo và điều chỉnh theo tải;
  Kafka, Elasticsearch, MySQL và hai JVM vẫn cần được theo dõi dung lượng RAM.
- AI là hướng phát triển, không chạy container AI và không cần cấu hình OpenAI.
- Dùng EBS đủ dung lượng cho MySQL, Kafka, Elasticsearch; bật snapshot/backup.
- Giữ SSH key riêng. Workflow dùng username ec2-user.
- Security Group: SSH chỉ cho nguồn cần thiết; 8083/8084 chỉ mở cho nguồn thử nghiệm
  hoặc reverse proxy. Middleware không publish các cổng ra host.
- Chưa có reverse proxy/HTTPS trong stack này. Thêm HTTPS trước khi phục vụ người dùng.
- Đây là mô hình một máy: EC2 hỏng sẽ ảnh hưởng cả ứng dụng và database.

Trên EC2, cài Docker và cho ec2-user sử dụng Docker:

```bash
sudo dnf install -y docker
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user
```

Đăng xuất/đăng nhập lại, rồi cài Docker Compose plugin theo
[hướng dẫn Docker](https://docs.docker.com/compose/install/linux/).
EC2 cần AWS CLI, Bash, flock và Docker Compose hỗ trợ --wait/--wait-timeout.
Kiểm tra:

```bash
docker version
docker compose version
aws --version
command -v flock
```

Elasticsearch cần vm.max_map_count tối thiểu 262144
([hướng dẫn Elastic](https://www.elastic.co/guide/en/elasticsearch/reference/8.10/docker.html)).
Áp dụng qua /etc/sysctl.d, ví dụ:

```bash
echo 'vm.max_map_count=262144' | sudo tee /etc/sysctl.d/99-bekoo-elasticsearch.conf
sudo sysctl --system
```

## 2. Tạo ECR và IAM

Tạo hai repository trong cùng region:

```bash
aws ecr create-repository --region ap-southeast-1 --repository-name bekoo-command
aws ecr create-repository --region ap-southeast-1 --repository-name bekoo-query
```

IAM identity dùng bởi GitHub Actions cần quyền push vào hai repository:
ecr:BatchCheckLayerAvailability, ecr:InitiateLayerUpload, ecr:UploadLayerPart,
ecr:CompleteLayerUpload, ecr:PutImage.
ecr:GetAuthorizationToken cần resource "*".

Gắn IAM Instance Role cho EC2, chỉ cần quyền pull:
ecr:BatchCheckLayerAvailability, ecr:GetDownloadUrlForLayer, ecr:BatchGetImage
cho hai repository, cùng ecr:GetAuthorizationToken.
Không cần copy AWS access key xuống EC2.

Sau khi pipeline ổn định, có thể chuyển GitHub Actions sang OIDC/IAM role.
Pipeline hiện dùng AWS access key giống Chiikaiwa-BE.

## 3. Chuẩn bị cấu hình runtime

Copy deploy/env.aws.example sang .env.aws (được Git bỏ qua) và điền giá trị thật.
Không dùng file .env local có DB_USER=root để deploy AWS.

- DB_URL: jdbc:mysql://mysql:3306/booking_care_command?createDatabaseIfNotExist=true.
- DB_USER: bekoo (không dùng root); DB_PASSWORD là mật khẩu user ứng dụng.
- MYSQL_ROOT_PASSWORD là một mật khẩu riêng.
- MYSQL_DATABASE phải khớp database trong DB_URL.
- Điền REDIS_PASSWORD, ELASTIC_PASSWORD và JWT_SECRET.
- JWT_SECRET là Base64 của ít nhất 32 byte ngẫu nhiên, dùng chung hai service.
- Điền cấu hình SMTP/Cloudinary/VNPay cho tính năng cần dùng.
- ADMIN_EMAIL/ADMIN_PASSWORD có thể để trống để không tự tạo admin.
- Public URL phải là địa chỉ thực tế, thay các domain example.com trong mẫu.

Docker Compose đọc file env và truyền biến cho container; giá trị chứa dấu $
nên được đặt trong nháy đơn theo
[quy tắc dotenv của Docker](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/).
Không dùng source để nạp file secret.

Tạo volume lần đầu sẽ khởi tạo user/mật khẩu MySQL. Đổi mật khẩu trong env
không đổi dữ liệu xác thực đã nằm trong volume MySQL/Elasticsearch.
Không chạy docker compose down -v trên dữ liệu cần giữ.
Backup MySQL ra ngoài EC2 và kiểm tra restore, không chỉ dựa vào volume Docker.

## 4. Khai báo GitHub Secrets

Repo → Settings → Secrets and variables → Actions:

| Secret | Nội dung |
|---|---|
| AWS_ACCESS_KEY_ID | Access key của IAM identity được phép push ECR |
| AWS_SECRET_ACCESS_KEY | Secret access key tương ứng |
| EC2_HOST | IP/DNS của EC2 Bekoo |
| EC2_SSH_KEY | Toàn bộ private key SSH của ec2-user |
| EC2_KNOWN_HOSTS | Dòng known_hosts của EC2 đã xác minh fingerprint |
| BEKOO_ENV | Toàn bộ nội dung .env.aws đã điền |

Để nạp env bằng CLI mà không hiển thị giá trị:

```bash
gh secret set BEKOO_ENV --repo Chaosql/Bekoo_HuongDichVu < .env.aws
```

EC2_KNOWN_HOSTS phải được xác minh với host key của chính EC2, không chỉ tin
kết quả ssh-keyscan. Pipeline bật StrictHostKeyChecking.
Repo public không có nghĩa Actions Secrets bị public.

## 5. Bật deployment

Repo chưa đủ cấu hình vẫn chạy build/test/image build, nhưng bỏ qua AWS deployment.
Sau khi EC2, ECR, IAM và tất cả secret đã sẵn sàng, tạo Repository Variables:

```text
AWS_REGION=ap-southeast-1
AWS_DEPLOY_ENABLED=true
```

Chạy thử Actions → Build and Deploy Bekoo to AWS EC2 → Run workflow.
Sau đó mỗi push main sẽ tự deploy.
Concurrency xếp hàng deployment, không hủy run đang thay container.

## 6. Điều gì xảy ra trên EC2

- Release nằm tại /home/ec2-user/bekoo/releases/<git-sha>.
- File .env được truyền qua SSH, permission 600.
- EC2 login ECR bằng IAM Instance Role.
- Pull cả image theo commit SHA và image middleware.
- Start MySQL, Redis, Kafka, Elasticsearch; chờ middleware healthy.
- Start Query trước, chờ /actuator/health.
- Start Command, chờ /actuator/health.
- Ghi nhận SHA thành công trong current-release.
- Khi app mới không healthy, thử khôi phục image app của release thành công trước.

Rollback chỉ áp dụng hai ứng dụng, không hoàn tác dữ liệu/schema hoặc mật khẩu
middleware. Lần deploy đầu chưa có release để rollback.
Startup health không thay thế smoke test Command → Kafka → Query → Elasticsearch.
Các tính năng AI được tắt mặc định và nằm ngoài phạm vi triển khai hiện tại.
Chưa có zero-downtime: thay container có thể gây gián đoạn ngắn.

Profile AWS chỉ expose endpoint health, không hiển thị chi tiết và tắt Swagger
mặc định. Có thể bật SWAGGER_ENABLED khi cần kiểm tra staging.
