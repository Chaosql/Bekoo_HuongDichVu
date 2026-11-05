# Deploy Bekoo_HuongDichVu lên AWS EC2

Bộ triển khai này học **luồng** trong `CHIIKAIWA-BE-AWS-DEPLOYMENT-GUIDE.md`, áp dụng cho kiến trúc thực của Bekoo: Java 17, thư viện `booking-care-document`, hai backend Command/Query, MySQL native trên EC2 và Kafka/Redis/Elasticsearch trong Docker. Không triển khai source Chiikaiwa, không cần PostgreSQL, Firebase, RDS, GHCR hay Tailscale.

```text
PR → Maven verify + kiểm tra script (không có quyền AWS/deploy)
Push main → verify → JAR artifact → build hai runtime image → Amazon ECR
         → SSH xác minh host key → runtime env 0600 → MySQL preflight
         → EC2 pull đúng SHA → health hai backend → rollback nếu lỗi
```

Build Java chạy trên GitHub Actions, EC2 chỉ nhận file cấu hình/script và pull image. Command và Query luôn dùng cùng commit SHA. `latest` được publish để tham khảo; deploy dùng SHA, không dùng `latest`. Workflow đợi deploy/rollback xong, không hủy giữa chừng khi có push mới.

## 1. File và vị trí runtime

| File | Mục đích |
|---|---|
| `.github/workflows/deploy-aws.yml` | Verify PR, build JAR, OIDC, push ECR, SCP và SSH deploy |
| `booking-server-{command,query}/aws.Dockerfile` | Runtime Java 17 non-root; copy đúng JAR đã verify |
| `application-aws.yml`, `logback-aws.xml` trong hai module | Profile production, log console, health nội bộ |
| `deploy/aws/compose.yaml` | Hai backend, Kafka, Redis, Elasticsearch, memory/log limits |
| `deploy/aws/env.aws.example` | Mẫu duy nhất để điền GitHub secret `BEKOO_ENV` |
| `prepare-release.py` | Tách secret thành command.env/query.env/infra.env, không source/eval |
| `check-mysql.py` | Thử MySQL từ đúng Docker bridge trước khi thay container |
| `server/activate-release.sh`, `server/deploy.sh` | Khóa deploy, cập nhật env, pull, xác minh image, health và rollback |
| `server/setup-network.sh`, `server/setup-mysql-ec2.sh` | Chuẩn bị bridge và MySQL native trên EC2 một lần |
| `mysql.sql.example`, `nginx.conf.example` | Mẫu provisioning database và domain |
| `server/backup-monthly.sh`, `bekoo-mysql-backup.*` | Backup MySQL mã hóa lên S3, timer tháng |

Trên EC2, dưới home của **cùng user SSH/Docker**:

```text
~/bekoo/
  incoming/<SHA>/     # runtime bundle nhận từ Actions; xóa sau deploy thành công
  runtime/
    compose.yaml
    command.env      # secret 0600
    query.env        # secret 0600
    infra.env        # secret 0600
    release.env      # ECR registry, SHA, cổng
    deploy.sh
    check-mysql.py
    releases.log
```

Toàn bộ cấu hình triển khai tập trung trong `deploy/aws/`. Việc sửa repo không tự tạo hạ tầng hay chuyển dữ liệu trên server.

## 2. Chuẩn bị EC2 một lần

Phương án hướng dẫn chính: **Ubuntu 24.04 hoặc 22.04**, Docker Engine và Compose plugin >= **2.30** (`env_file.format: raw`), AWS CLI v2. x86 dùng `AWS_PLATFORM=linux/amd64`; Graviton dùng `linux/arm64`. Runtime stack có giới hạn RAM container tổng khoảng 4.75 GiB, chưa tính MySQL/OS; dành khoảng 8 GiB RAM trở lên và kiểm tra tải thực tế. Không giả định instance đủ miễn phí hoặc stack chạy được trên máy 1 GiB.

1. Tạo EC2, storage đủ cho database/images/volumes; kiểm tra giá và hạn mức trong account.
2. Security Group: public **80/443**; SSH **22** chỉ từ nguồn quản trị/CI được kiểm soát. Không public 3306, 6379, 9092, 9200, 8083, 8084.
3. Workflow dùng SSH trực tiếp tới `EC2_HOST`. GitHub-hosted runner không có một IP cố định: dùng runner có egress IP cố định hoặc self-hosted runner có đường tới EC2, cấu hình SG cho đúng nguồn. Nếu dùng self-hosted runner, đổi `runs-on` **của job release**; job verify PR giữ runner riêng, không chạy PR không tin cậy trên runner deploy. Không mở SSH toàn Internet để xử lý lỗi timeout. Private EC2 cần runner có route vào VPC hoặc cơ chế kết nối quản trị riêng.
4. Cài Docker từ [kho chính thức](https://docs.docker.com/engine/install/ubuntu/), AWS CLI v2 từ [hướng dẫn AWS](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html). Trên Graviton chọn bản CLI aarch64; trên x86 chọn x86_64.
5. Dùng user `ubuntu` mặc định hoặc user deploy riêng; cấp quyền Docker cho user này (quyền Docker tương đương root). Thêm public key CI vào `~/.ssh/authorized_keys`. Không copy private SSH key vào repo.

```bash
sudo apt update
sudo apt install -y curl jq python3 nginx age gzip openssh-server
sudo systemctl enable --now docker nginx ssh
sudo sysctl -w vm.max_map_count=262144
printf 'vm.max_map_count=262144\n' | sudo tee /etc/sysctl.d/90-bekoo-elasticsearch.conf
uname -m
free -h
df -h
docker compose version
aws --version
```

Amazon Linux: cài Docker, Compose, AWS CLI và **MySQL chính thức tương thích OS** bằng hướng dẫn riêng. Không chạy apt/installer Ubuntu trên Amazon Linux; việc dùng SSH user `ec2-user` không tự làm installer tương thích.

## 3. MySQL native, bridge và schema

Không có MySQL server container trong stack. MySQL trên EC2 lắng nghe tại gateway cố định **172.30.83.1:3306** của external bridge **bekoo-backend**, subnet **172.30.83.0/24**. Container Command ánh xạ `bekoo.mysql.internal` tới địa chỉ đó. Đây là IP cố định của bridge Bekoo, không phải `host-gateway` mặc định và không phải loopback container.

Từ máy phát triển, chuyển **bộ script provisioning** sang EC2 (không chuyển source Java):

```bash
tar -czf /tmp/bekoo-aws-runtime.tar.gz deploy/aws
scp /tmp/bekoo-aws-runtime.tar.gz ubuntu@YOUR_EC2_HOST:/tmp/
```

Trên EC2:

```bash
mkdir -p /tmp/bekoo-provision
cd /tmp/bekoo-provision
tar -xzf /tmp/bekoo-aws-runtime.tar.gz
ip route
docker network ls
bash deploy/aws/server/setup-network.sh --create
# CHỈ cho Ubuntu mới, chưa có MySQL/MariaDB/dữ liệu hay cổng 3306 đang dùng:
sudo bash deploy/aws/server/setup-mysql-ec2.sh --install-fresh
```

Installer từ chối máy có database hiện hữu, không import/drop/reset database. Với MySQL đã tồn tại: backup trước; cấu hình thủ công `bind-address=172.30.83.1` (hoặc thêm địa chỉ này nếu đang phục vụ app khác), tắt MySQL X nếu không dùng và đặt service khởi động sau Docker. Không thay bind-address đang dùng bởi dự án khác một cách máy móc. Bridge external không bị xóa bởi `compose down`.

Áp dụng firewall host cho nguồn subnet Bekoo tới 3306, chặn nguồn khác; SG không mở 3306. Kiểm tra quy tắc Docker/iptables, không chỉ dựa vào UFW. Nếu subnet đã trùng mạng có sẵn, đổi đồng bộ network script, Compose, URL mapping, preflight, MySQL bind/grants và firewall trước khi dùng.

```bash
sudo systemctl status mysql --no-pager
sudo ss -lntp | grep ':3306'
docker network inspect bekoo-backend
```

Sửa mật khẩu trong `deploy/aws/mysql.sql.example` rồi chạy bằng MySQL administrator. Backend dùng user **bekoo_command**, database **booking_care_command**, quyền runtime DML/EXECUTE, host giới hạn subnet. Không dùng root cho backend. Secret GitHub phải khớp tài khoản đã tạo.

**Schema:** profile AWS mặc định `DB_DDL_AUTO=validate`. Dự án chưa có Flyway/Liquibase; database rỗng chưa chạy được ngay. Chọn một cách:

- Có dữ liệu cũ: dump/restore vào MySQL trên EC2, dừng ghi khi chuyển dữ liệu cuối và kiểm tra schema/row count/API.
- Database hoàn toàn mới: cấp tạm `CREATE, ALTER, INDEX, REFERENCES` trên database cho user ứng dụng; đặt `DB_DDL_AUTO=update` trong `BEKOO_ENV`; deploy để tạo schema, kiểm tra bảng; đổi secret lại `validate`, thu hồi quyền DDL và chạy workflow lại. Script recreate kể cả cùng SHA để áp dụng runtime env mới.

Không chạy lại `update` như migration production mặc định. Các thay đổi schema sau này cần migration được review; rollback image không rollback dữ liệu/schema.

Preflight CD dùng client image `mysql:8.0`, chạy `SELECT 1` trên network ứng dụng, truyền mật khẩu qua environment, không command line/log. Kiểm tra này xác nhận kết nối, user và database; không thay thế validate schema hay kiểm tra nghiệp vụ. EC2 cần pull được image client và các image hạ tầng từ registry tương ứng.

## 4. ECR và IAM

Tạo trước hai private ECR repository trong region đã chọn:

```text
bekoo-command
bekoo-query
```

Cấu hình scanning/lifecycle phù hợp ngân sách, giữ đủ image SHA để rollback. Workflow publish `SHA` và `latest`; giữ tag `latest` có thể cập nhật. Không ghi đè SHA đã phát hành; nếu bật immutable tags, phải tạo ngoại lệ cho latest và xử lý rerun SHA đã tồn tại theo policy của bạn (workflow hiện push lại tag khi rerun).

**GitHub OIDC role:** tạo IAM OIDC provider `https://token.actions.githubusercontent.com`, audience `sts.amazonaws.com`. Trust policy giới hạn đúng repo và Environment:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"},
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {"StringEquals": {
      "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
      "token.actions.githubusercontent.com:sub": "repo:Chaosql/Bekoo_HuongDichVu:environment:production"
    }}
  }]
}
```

Role push ECR cần `ecr:GetAuthorizationToken` trên `*`; trên đúng hai repository ARN cấp `ecr:BatchCheckLayerAvailability`, `ecr:InitiateLayerUpload`, `ecr:UploadLayerPart`, `ecr:CompleteLayerUpload`, `ecr:PutImage`, `ecr:BatchGetImage`, `ecr:GetDownloadUrlForLayer`. Không cần quyền tạo/xóa EC2/database hay AdministratorAccess.

**EC2 Instance Role:** trust service `ec2.amazonaws.com`; cấp pull ECR: `ecr:GetAuthorizationToken` trên `*`, `ecr:BatchCheckLayerAvailability`, `ecr:GetDownloadUrlForLayer`, `ecr:BatchGetImage` trên hai repository ARN. Gắn instance profile vào EC2. Không chạy `aws configure` để lưu access key dài hạn trên EC2. `deploy.sh` đăng nhập lại ECR mỗi lần bằng role EC2; không nhận credential AWS từ runner.

Nếu dùng backup S3, cấp thêm `s3:PutObject` trên `arn:aws:s3:::YOUR_BUCKET/mysql-monthly/*`; người restore/giám sát dùng role riêng với quyền đọc/list cần thiết. Bucket SSE-KMS cần quyền KMS tương ứng. Giữ S3 Block Public Access bật.

Tham khảo: [GitHub OIDC AWS action](https://github.com/aws-actions/configure-aws-credentials), [ECR authentication](https://docs.aws.amazon.com/AmazonECR/latest/userguide/registry_auth.html).

## 5. GitHub variables và secrets của Bekoo

Repository Settings → Actions cho phép workflow. Tạo Environment **production**, giới hạn deployment branch **main**, approvals tùy nhu cầu.

**Repository variables** (đặt tại repository vì điều kiện job được đánh giá trước Environment):

| Variable | Giá trị |
|---|---|
| AWS_DEPLOY_ENABLED | `true` khi EC2/IAM/secret sẵn sàng; chưa đặt thì chỉ CI verify |
| AWS_REGION | Ví dụ `ap-southeast-1` |
| AWS_PLATFORM | `linux/amd64` cho x86, `linux/arm64` cho Graviton |
| EC2_SSH_USER | `ubuntu` mặc định, hoặc user deploy thực tế |

**Environment production secrets:**

| Secret | Nội dung |
|---|---|
| AWS_ROLE_ARN | ARN IAM role push ECR qua GitHub OIDC |
| EC2_HOST | Public IPv4/DNS EC2 hoặc hostname reachable từ runner |
| EC2_SSH_KEY | Private key CI khớp authorized_keys của user SSH |
| EC2_KNOWN_HOSTS | Dòng known_hosts đúng EC2_HOST, xác minh qua kênh tin cậy |
| BEKOO_ENV | Toàn bộ nội dung `deploy/aws/env.aws.example` đã điền |

Không cần `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, Firebase hay các secret riêng của Chiikaiwa.

Lấy SSH host public key qua console/kênh quản trị tin cậy trên EC2; đối chiếu `sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`. Dòng known_hosts có dạng `YOUR_EC2_HOST ssh-ed25519 AAAA...` với key thật. Không tắt host checking hay tự tin `ssh-keyscan` trong CI.

**BEKOO_ENV:** giá trị thô `KEY=value`, không dấu nháy bao quanh, không `export`, không giá trị nhiều dòng. `$` được giữ nguyên nhờ Compose `format: raw`. JWT là Base64 của ít nhất 32 byte ngẫu nhiên (`openssl rand -base64 48`). Mỗi secret Redis/Elasticsearch/JWT trong BEKOO_ENV được công cụ tự chép đồng nhất vào các service cần dùng. Các trường SMTP, Cloudinary, VNPay, admin tùy chức năng dự án; để trống thì chức năng tương ứng chưa được cấu hình. AI vẫn tắt mặc định.

`SPRING_COMMAND_URL`, `SPRING_QUERY_URL` trong secret được tách thành `SPRING_URL` riêng từng backend. Mẫu mặc định:

```dotenv
SPRING_COMMAND_URL=https://bekoo-command.chiikaiwa.me
SPRING_QUERY_URL=https://bekoo-query.chiikaiwa.me
WEB_URL=https://chiikaiwa.me/home
VNPAY_RETURN_URL=https://bekoo-command.chiikaiwa.me/payment/result
```

`WEB_URL` phải là frontend thật của bạn nếu frontend host ở nơi khác.

## 6. Deploy lần đầu và các lần sau

1. Hoàn tất EC2, network, MySQL/schema, role, registry, DNS và secrets theo các mục trên.
2. Bật repository variable `AWS_DEPLOY_ENABLED=true` rồi push main hoặc chạy workflow thủ công trên main.
3. Job verify build thư viện document trước, chạy Maven `clean verify -Dtest=*Test` cho Command/Query; toàn bộ unit test `*Test` phải pass. Hai context `*ApplicationTests` cần hạ tầng live không thuộc tập unit test này.
4. Artifact chỉ chứa đúng hai executable JAR, dùng lại ở job release; không build Maven lần nữa trên EC2.
5. Release qua OIDC push hai image, truyền runtime bundle bằng SCP và chạy activation qua SSH. Runtime secret 0600, thư mục 0700. Không in `.env`/`docker compose config` thật ra log.
6. Trên EC2: khóa deploy → preflight bridge/MySQL → đăng nhập ECR bằng Instance Role → pull/verify revision hai image → chờ hạ tầng healthy → recreate hai backend → đối chiếu image ID và `/actuator/health` cả hai.

Chạy dưới đúng user SSH để kiểm tra:

```bash
cd ~/bekoo/runtime
docker compose -p runtime --env-file release.env -f compose.yaml ps
curl -fsS http://127.0.0.1:8083/actuator/health
curl -fsS http://127.0.0.1:8084/actuator/health
```

Không `source release.env`; script loại biến shell có thể ghi đè release khi gọi Compose. Cùng SHA vẫn recreate để cập nhật app env. Nếu khác `compose.yaml` hoặc `infra.env` đã cài, CD **dừng trước khi ghi env ứng dụng**: thay đổi topology/mật khẩu Redis/Elasticsearch cần review và maintenance riêng, không tự xoay trong một lần deploy backend. Elasticsearch có dữ liệu sẵn không đổi mật khẩu chỉ bằng sửa env; phải đổi trên service.

Có downtime ngắn khi recreate. Nếu health/image check lỗi và nhận diện được cùng một SHA cũ cho cả hai backend, script khôi phục app env trước đó và rollback cả hai. Image cũ phải còn local/ECR. Khi deploy lần đầu hoặc lỗi với cùng SHA không có release khác, script báo phục hồi thủ công; xem container logs và health. Không xóa container/volume để xử lý lỗi một cách mặc định.

Rollback thủ công tới SHA đã biết, dùng runtime env hiện tại (DB phải tương thích):

```bash
APPS_ROOT="$HOME/bekoo" bash "$HOME/bekoo/runtime/deploy.sh" runtime OLD_FULL_40_CHARACTER_SHA
```

`SIGKILL`, mất điện hoặc Docker daemon chết giữa deploy không bảo đảm rollback tức thời; sau reboot đối chiếu image/release.env và health. Tránh `docker system prune -a`/`compose down -v`; chúng có thể làm mất image rollback/dữ liệu.

## 7. Domain chiikaiwa.me, Nginx và HTTPS

Trong DNS Namecheap, thêm hai A record:

| Host | Value |
|---|---|
| bekoo-command | Public IPv4 EC2 |
| bekoo-query | Public IPv4 EC2 |

DNS dùng IP public EC2; cân nhắc địa chỉ ổn định và kiểm tra phí IPv4/Elastic IP. Không thay record domain gốc nếu đang phục vụ website khác.

Cài `nginx.conf.example` vào `/etc/nginx/sites-available/bekoo.conf`, symlink vào `sites-enabled`, sửa domain/cổng nếu cần. Cấu hình proxy loopback 8083/8084, chặn actuator public, giới hạn upload 12 MiB cho Command.

```bash
sudo nginx -t
sudo systemctl reload nginx
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d bekoo-command.chiikaiwa.me -d bekoo-query.chiikaiwa.me
```

Frontend dùng hai base URL đầy đủ `https://bekoo-command.chiikaiwa.me` và `https://bekoo-query.chiikaiwa.me` kèm API path. DNS phải trỏ đúng và SG cho 80/443 trước khi cấp TLS.

## 8. Backup MySQL lên S3

Backup lên **S3** vào ngày **01 lúc 10:00 Asia/Ho_Chi_Minh**. MySQL native cần backup độc lập với deploy/rollback image.

- Tạo bucket private, lifecycle khoảng 185 ngày (~6 kỳ, không chính xác tuyệt đối 6 file); giám sát chi phí/disk và job thất bại.
- Tạo user backup theo SQL mẫu. Vì MySQL bind bridge IP, `/root/.my-backup.cnf` dùng **host=172.30.83.1**, grant user backup cũng theo địa chỉ này. Kiểm tra nguồn TCP thực tế và phiên bản MySQL (`SHOW_ROUTINE` dành MySQL 8.0.20+).
- `backup.conf.example` → `/etc/bekoo-mysql-backup.conf`; `my-backup.cnf.example` → `/root/.my-backup.cnf`, permission 0600.
- Điền region, bucket và age public recipient. Cất age private key giải mã ngoài EC2.

```bash
sudo install -d -m 755 /opt/devops
sudo install -m 700 deploy/aws/server/backup-monthly.sh /opt/devops/backup-monthly.sh
sudo install -m 644 deploy/aws/server/bekoo-mysql-backup.service /etc/systemd/system/
sudo install -m 644 deploy/aws/server/bekoo-mysql-backup.timer /etc/systemd/system/
sudo chmod 600 /etc/bekoo-mysql-backup.conf /root/.my-backup.cnf
sudo systemctl daemon-reload
sudo systemd-analyze calendar '*-*-01 10:00:00 Asia/Ho_Chi_Minh'
sudo systemctl start bekoo-mysql-backup.service
sudo journalctl -u bekoo-mysql-backup.service -n 60 --no-pager
# Chỉ bật sau khi dump/upload và restore thử thành công:
sudo systemctl enable --now bekoo-mysql-backup.timer
```

Script dùng `mysqldump --single-transaction --routines --events --triggers --no-tablespaces` → gzip → age → `aws s3 cp` và checksum tương đối. Instance Role EC2 cung cấp quyền S3; không đặt access key trong backup config.

Restore drill: tải `.age` và `.sha256`, `sha256sum -c FILE.sha256`, giải mã với age private key, giải nén rồi import vào **MySQL test instance riêng** vì dump chứa CREATE DATABASE/USE. Kiểm tra bảng/row count/API. Backup tháng có thể mất gần một tháng thay đổi. Backup MySQL chưa bao gồm Kafka/Redis/Elasticsearch; cần snapshot/export hoặc replay/reindex đã kiểm thử nếu muốn khôi phục toàn bộ trạng thái CQRS.

## 9. Checklist trước production

- Build/test/workflow/config pass; CPU image khớp EC2; role push/pull đúng hai ECR repository.
- MySQL user/grants/bind/firewall được thử từ Docker bridge; 3306/Redis/Kafka/Elasticsearch không public.
- Thử deploy đầu, cùng SHA sau thay env, SHA mới, pull lỗi, health lỗi và rollback thật trên EC2.
- Login và luồng ghi Command → Kafka → Query/Elasticsearch hoạt động; thử SMTP/upload/VNPay nếu dùng.
- Nginx/TLS đúng domain; health chỉ nội bộ; kiểm tra reboot và disk/RAM.
- Backup/upload/restore test thành công, có retention và cảnh báo lỗi/lỡ lịch.

Bộ file được kiểm tra local; repo không tự tạo EC2/ECR/IAM hay thay đổi GitHub Secrets. Không coi kiểm tra mô phỏng rollback là xác nhận hệ thống đã chạy end-to-end trên AWS.
