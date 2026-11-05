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

## 2. Amazon Linux 2023 / máy demo 4 GiB hiện tại

Mục tiêu hiện tại: **Amazon Linux 2023 x86_64**, user **ec2-user**, region **ap-southeast-1**, Elastic IP đã xác minh **54.255.60.109**. Máy đã nâng từ 2 GiB lên 4 GiB; MySQL Community **8.4.13 EL9** đã được cài bằng DNF nhưng chưa cấu hình/chạy. Đây là phiên bản package đã kiểm tra dependency trên máy của bạn; MySQL không liệt kê AL2023 trong nền tảng Yum được hỗ trợ chính thức. Không dùng script Ubuntu hoặc `apt`.

Mặc định Compose đã chỉnh cho demo **2–3 người**:

| Service | Heap Java | Container RAM tối đa |
|---|---|---|
| Command | 96–256 MiB | 576 MiB |
| Query | 96–224 MiB | 512 MiB |
| Kafka | 128–192 MiB | 448 MiB |
| Elasticsearch | 256 MiB | 768 MiB |
| Redis | maxmemory 48 MiB, noeviction | 96 MiB |

Tổng giới hạn container **2400 MiB (~2.34 GiB)**. MySQL có buffer pool 128 MiB, tối đa 20 kết nối; đây không phải giới hạn RSS của MySQL. Phần còn lại dành cho OS/Chiikaiwa/PostgreSQL hiện có. Giữ swap 2 GiB đã có. Đây là cấu hình thử nghiệm, cần đo RAM khi chạy thật; không bảo đảm chạy ổn định cùng các ứng dụng khác chỉ dựa trên số người dùng. Khi thiếu RAM, giảm tải hoặc tạm dừng ứng dụng khác trong cửa sổ demo bằng quyết định của bạn; script không dừng Chiikaiwa/PostgreSQL/Redis cũ.

Compose phải >= **2.30** (hoặc 5.x) và AWS CLI v2. Docker hiện hữu được giữ nguyên, không cài lại/restart trong luồng backend deploy.

```bash
sudo dnf install -y curl jq python3 nginx openssl tar gzip
uname -m
free -h
swapon --show
docker compose version
aws --version
```

Nếu Compose thiếu/cũ, cài plugin x86_64 cho user ec2-user theo [Docker](https://docs.docker.com/compose/install/linux/). Ví dụ phiên bản trong hướng dẫn Docker hiện tại:

```bash
mkdir -p ~/.docker/cli-plugins
curl -fL https://github.com/docker/compose/releases/download/v5.6.0/docker-compose-linux-x86_64 -o ~/.docker/cli-plugins/docker-compose
chmod +x ~/.docker/cli-plugins/docker-compose
docker compose version
```

Dùng cùng user `ec2-user` cho Docker/SSH; không cài plugin chỉ cho root rồi deploy bằng ec2-user. Nếu AWS CLI chưa có, cài bản Linux x86_64 theo [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html).

Demo bằng IP: Security Group mở TCP 8083 và 8084 cho người test; SSH 22 từ nguồn quản trị/CI được kiểm soát; không public 3306, 6379, 9092, 9200. Redis cũ đang publish 6379: kiểm tra SG để chắc chắn không cho Internet truy cập. Workflow dùng SSH trực tiếp: GitHub-hosted runner không có IP cố định, nên cần runner có egress IP cố định hoặc self-hosted runner có route tới EC2 và đổi `runs-on` của **job release**. Job PR verify vẫn dùng GitHub-hosted runner, không dùng runner deploy cho PR không tin cậy.

## 3. Chạy script cho MySQL đã cài trên server này

Từ **máy phát triển**, tại thư mục gốc repo sau khi có các thay đổi mới:

```bash
tar --exclude=__pycache__ --exclude='*.pyc' --exclude='*.env' --exclude=backup.conf --exclude=my-backup.cnf -czf /tmp/bekoo-aws-runtime.tar.gz deploy/aws
scp /tmp/bekoo-aws-runtime.tar.gz ec2-user@54.255.60.109:/tmp/
```

Nếu key SSH không nằm trong SSH agent, thêm `-i /PATH/TO/YOUR_KEY.pem` vào scp/ssh. Archive chỉ chứa runtime/templates/scripts, không có source Java hay secrets thật.

Trên **EC2**, chạy bằng user ec2-user (các script được thực thi bằng bash, dùng được dù shell đăng nhập là fish):

```bash
mkdir -p ~/bekoo-provision
tar -xzf /tmp/bekoo-aws-runtime.tar.gz -C ~/bekoo-provision
cd ~/bekoo-provision
sudo bash deploy/aws/server/setup-mysql-ec2.sh --configure-existing
```

Đây là lệnh đúng cho máy hiện tại vì package MySQL đã cài. Script kiểm tra Amazon Linux 2023 x86_64/MySQL 8.4, tạo/kiểm tra bridge `bekoo-backend` (172.30.83.0/24, gateway 172.30.83.1), sao lưu cấu hình, cài `mysql-demo.cnf`, kiểm tra `mysqld --validate-config`, rồi enable/start **mysqld.service**. Nó không xóa/khởi tạo lại thư mục dữ liệu, không đổi mật khẩu hay tạo/drop schema. Nếu có MySQL đang chạy mà chưa có cấu hình Bekoo do script quản lý, script từ chối thay đổi để không ảnh hưởng database khác.

MySQL chỉ bind **127.0.0.1 và 172.30.83.1**, không bind public interface. `bekoo.mysql.internal` trong Command ánh xạ tới gateway này. Systemd kiểm tra/tạo lại bridge bằng script root trước khi MySQL khởi động sau reboot. Kiểm tra subnet không trùng `ip route`; nếu trùng, không xóa network hiện có mà phải điều chỉnh đồng bộ cấu hình. Giới hạn firewall host cho subnet Bekoo tới 3306; SG không mở database ra ngoài.

Cho một máy AL2023 x86_64 khác chưa cài MySQL, tùy chọn `--install-fresh` sẽ cài 8.4 từ repo EL9, giữ kiểm tra GPG, từ chối nếu package/dữ liệu đã tồn tại. Không dùng tùy chọn này trên máy bạn vừa cài. Script lưu repo `bekoo-mysql84` để các lần cập nhật MySQL sau có nguồn, không đổi global releasever của Amazon Linux.

Kiểm tra:

```bash
sudo systemctl status mysqld --no-pager
sudo ss -lntp | grep ':3306'
docker network inspect bekoo-backend
```

**Đăng nhập root lần đầu:** RPM tạo mật khẩu tạm khi service khởi động lần đầu. Xem riêng trên terminal (không gửi/log mật khẩu này vào chat):

```bash
sudo grep 'temporary password' /var/log/mysqld.log
sudo env MYSQL_HISTFILE=/dev/null mysql --connect-expired-password -u root -p
```

Trong MySQL, đổi mật khẩu root (thay placeholder bằng mật khẩu mạnh thực tế), rồi thoát:

```sql
ALTER USER 'root'@'localhost' IDENTIFIED BY 'REPLACE_WITH_STRONG_ROOT_PASSWORD';
EXIT;
```

Sửa `deploy/aws/mysql.sql.example` trên EC2 bằng editor với password thật, rồi đăng nhập root, `SOURCE` file SQL đó:

```bash
sudo env MYSQL_HISTFILE=/dev/null mysql -u root -p
```

```sql
SOURCE /home/ec2-user/bekoo-provision/deploy/aws/mysql.sql.example;
```

File SQL tạo database **booking_care_command**, user **bekoo_command** chỉ từ subnet Docker và user backup riêng. Không dùng root cho backend. Mật khẩu user ứng dụng phải khớp `DB_PASSWORD` trong GitHub `BEKOO_ENV`; file SQL đã điền mật khẩu phải giữ ngoài Git và chmod 600. Không chạy lại `CREATE USER` nếu user đã tồn tại; quản trị user hiện hữu riêng.

**Database mới chưa có bảng:** mặc định `DB_DDL_AUTO=validate` sẽ không tạo bảng. Trong MySQL cấp quyền bootstrap tạm:

```sql
GRANT CREATE, ALTER, INDEX, REFERENCES ON booking_care_command.* TO 'bekoo_command'@'172.30.83.0/255.255.255.0';
```

Đặt `DB_DDL_AUTO=update` trong GitHub secret cho lần deploy đầu, xác nhận các bảng/API hoạt động; sau đó đổi lại `validate`, thu hồi các quyền DDL tạm và chạy workflow lại. Dự án chưa có Flyway/Liquibase; các thay đổi schema sau này cần review, không tự động rollback DB khi rollback image.

```sql
REVOKE CREATE, ALTER, INDEX, REFERENCES ON booking_care_command.* FROM 'bekoo_command'@'172.30.83.0/255.255.255.0';
```

Có dữ liệu cũ: dump/restore có kiểm soát thay vì bootstrap rỗng. Preflight CD dùng MySQL client container chạy SELECT 1 trên bridge trước khi thay backend; nó không cài/restart MySQL native.

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
| EC2_SSH_USER | `ec2-user` (mặc định cho Amazon Linux hiện tại) |

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
6. Trên EC2: khóa deploy → preflight bridge/MySQL → đăng nhập ECR bằng Instance Role → pull/verify revision hai image → chờ hạ tầng healthy → khởi động Command và chờ healthy, rồi Query → đối chiếu image ID và `/actuator/health` cả hai.

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

## 7. Truy cập demo bằng IP và cổng

Không cần DNS hoặc Nginx cho luồng demo hiện tại. Trong Security Group của EC2, thêm inbound TCP 8083 và 8084 từ IP của người test (hoặc 0.0.0.0/0 nếu cần truy cập công khai).

| Backend | Base URL | Swagger |
|---|---|---|
| Command | http://54.255.60.109:8083 | http://54.255.60.109:8083/swagger-ui/index.html |
| Query | http://54.255.60.109:8084 | http://54.255.60.109:8084/swagger-ui/index.html |

Trong `.env.aws` / secret `BEKOO_ENV`, dùng `SPRING_COMMAND_URL=http://54.255.60.109:8083`, `SPRING_QUERY_URL=http://54.255.60.109:8084`, `SWAGGER_ENABLED=true`. `VNPAY_RETURN_URL` dùng cùng IP/cổng Command với path `/payment/result`. `WEB_URL` vẫn là địa chỉ frontend thực tế.

Compose publish hai cổng trên mọi interface. Khi chuyển từ bản chỉ bind loopback, cập nhật `~/bekoo/runtime/compose.yaml` trong lần bảo trì trước khi chạy workflow, vì CD sẽ từ chối thay đổi topology tự động. Chỉ recreate Command và Query, giữ các volume và dịch vụ hạ tầng.

Frontend dùng base URL đầy đủ tương ứng rồi nối API path. Frontend chạy HTTPS sẽ bị trình duyệt chặn khi gọi backend HTTP (mixed content); với demo này có thể dùng Swagger trực tiếp hoặc frontend HTTP/local. Mẫu `nginx.conf.example` dành cho khi cần bổ sung domain/HTTPS sau này.

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
- Hai cổng 8083/8084 và Swagger truy cập được bằng IP; kiểm tra reboot và disk/RAM.
- Backup/upload/restore test thành công, có retention và cảnh báo lỗi/lỡ lịch.

Bộ file được kiểm tra local; repo không tự tạo EC2/ECR/IAM hay thay đổi GitHub Secrets. Không coi kiểm tra mô phỏng rollback là xác nhận hệ thống đã chạy end-to-end trên AWS.
