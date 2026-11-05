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
