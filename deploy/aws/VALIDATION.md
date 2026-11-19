# Kiểm tra bộ deploy AWS — 03/11/2026

Đã thực hiện trên máy phát triển Linux x86_64, JDK 17:

- Thư viện `booking-care-document`: Maven `clean install` thành công.
- Command/Query: Maven `clean verify -Dtest=*Test` thành công; 8 unit test Command và 1 unit test Query, không lỗi.
- Cả hai JAR có `application-aws.yml`, `logback-aws.xml`; không còn cấu hình OCI.
- Hai `aws.Dockerfile` build thành công với tag local `bekoo-aws-command:validation` và `bekoo-aws-query:validation` (amd64); không push registry.
- 14 bài kiểm tra runtime: deploy lần đầu, cùng SHA cập nhật env, pull lỗi, sai revision/image ID, database/infra lỗi, health lỗi, rollback hai backend, tách secret không nội suy `$`, reject cấu hình DB sai, chặn thay infra không kiểm soát và activation thất bại khôi phục env cũ.
- actionlint v1.7.12 chấp nhận workflow AWS; metadata của tất cả Actions pin SHA xác minh qua repository chính thức.
- Compose `config --quiet` với env mẫu và `bash -n` trên các script đều pass.
- systemd chấp nhận lịch ngày 01, 10:00 Asia/Ho_Chi_Minh; kỳ tiếp theo 01/12/2026.

Chưa chạy workflow trên GitHub, chưa tạo EC2/ECR/IAM/S3, chưa thay GitHub secrets, chưa chạy end-to-end trên AWS. Chưa chạy application image ARM64; `*ApplicationTests` phụ thuộc hạ tầng live không nằm trong tập unit test trên. Cần kiểm chứng MySQL/Kafka/Redis/Elasticsearch, API CQRS, TLS, backup/upload/restore và rollback thực tế trên EC2 theo SETUP-AWS.md.

## Amazon Linux 2023 / demo 4 GiB — 05/11/2026

- Provisioning chuyển sang AL2023 x86_64 và mysqld.service. Chế độ --configure-existing dùng package MySQL 8.4 đã cài; từ chối thay cấu hình MySQL khác đang chạy, sao lưu cấu hình và phục hồi nếu validate-config lỗi. Không thay đổi schema/mật khẩu/dữ liệu.
- Giảm container RAM xuống tổng 2400 MiB, Hikari 3 kết nối, Tomcat 20 thread; startup Command rồi Query sau health. Elasticsearch tắt module ML không dùng.
- 19 kiểm tra provisioning/deploy/secret/rollback chạy bằng fake tools; có bài kiểm tra Query không được start nếu Command mới chưa healthy.
- File mysql-demo.cnf được mysqld của image mysql:8.4 chấp nhận qua --validate-config trong container tạm.
- Chạy thật Kafka/Redis/Elasticsearch với memory limits cuối cùng trên máy phát triển: cả ba healthy; quan sát nhàn rỗi khoảng Elasticsearch 686–692 MiB/768 MiB, Kafka 231–233 MiB/448 MiB, Redis 9 MiB/96 MiB trong khoảng 30 giây sau health. Project/volume test đã được dọn; không chạm container hiện hữu.
- Workflow qua actionlint, shell qua bash -n, Compose/Spring YAML parse thành công.
- Chưa chạy hai backend với workload trong profile demo trên EC2, chưa cấu hình MySQL native trên EC2 bằng script mới và chưa deploy end-to-end AWS. Các số RAM trên không bảo đảm tải thật/đỉnh startup hay khả năng chia sẻ máy với Chiikaiwa. Kiểm tra OOM/restarts, health và luồng CQRS sau khi deploy.
