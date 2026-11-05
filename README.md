# Bekoo_HuongDichVu

Backend Bekoo gồm thư viện sự kiện `booking-care-document`, Command dùng MySQL và Query dùng Elasticsearch; hai backend trao đổi qua Kafka và dùng Redis. Repository: [Chaosql/Bekoo_HuongDichVu](https://github.com/Chaosql/Bekoo_HuongDichVu). Giữ nguyên [LICENSE](LICENSE).

## Deploy AWS EC2

Luồng duy nhất: **GitHub Actions build/test → Amazon ECR → SSH EC2 → Docker Compose → health check/rollback**. Hai backend deploy cùng commit SHA. MySQL cài trực tiếp trên EC2; Kafka, Redis và Elasticsearch chạy trong container. EC2 không build source Java.

- [Hướng dẫn setup EC2, MySQL, ECR, IAM, DNS và GitHub Secrets](deploy/aws/SETUP-AWS.md)
- [Mẫu cấu hình GitHub secret BEKOO_ENV](deploy/aws/env.aws.example)
- [Workflow CI/CD](.github/workflows/deploy-aws.yml)
- [Kết quả kiểm tra](deploy/aws/VALIDATION.md)

Bật repository variable `AWS_DEPLOY_ENABLED=true` sau khi hoàn tất hạ tầng và secrets. Khi chưa bật, workflow chỉ chạy verify. Secret thật không được commit; runtime env trên EC2 có quyền 0600.

## Build và kiểm tra

Yêu cầu Java 17. GitHub Actions thực hiện các lệnh tương ứng:

```bash
bash booking-server-query/mvnw -B -f booking-care-document/pom.xml clean install
bash booking-server-command/mvnw -B -f booking-server-command/pom.xml clean verify '-Dtest=*Test'
bash booking-server-query/mvnw -B -f booking-server-query/pom.xml clean verify '-Dtest=*Test'
python3 -m unittest discover -s deploy/aws/tests -v
```

Hai context test `*ApplicationTests` cần hạ tầng live; kiểm chứng end-to-end trên EC2 theo checklist trong hướng dẫn AWS. AI tắt mặc định; SMTP, Cloudinary, VNPay và admin cần cấu hình tương ứng nếu sử dụng.
