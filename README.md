# Bekoo - ServerSide

[![GitHub License](https://img.shields.io/github/license/Chaosql/Bekoo_HuongDichVu)](LICENSE)
[![GitHub contributors](https://img.shields.io/github/contributors/Chaosql/Bekoo_HuongDichVu)](https://github.com/Chaosql/Bekoo_HuongDichVu/graphs/contributors)
[![CI and AWS deployment](https://github.com/Chaosql/Bekoo_HuongDichVu/actions/workflows/deploy-aws.yml/badge.svg)](https://github.com/Chaosql/Bekoo_HuongDichVu/actions/workflows/deploy-aws.yml)

## Table of contents

- [Introduction](#introduction)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation and deployment](#installation-and-deployment)
- [API documentation](#api-documentation)
- [Build and verification](#build-and-verification)
- [Contributing](#contributing)
- [Contact](#contact)
- [License](#license)

## Introduction

**Bekoo** — Your health, simplified. Book a doctor's appointment anytime, anywhere. Select a preferred doctor, choose a convenient time slot, and manage appointments through a healthcare booking system.

This repository contains the Bekoo backend, implemented with Java 17 and Spring Boot. It separates commands and queries using CQRS and exchanges events through Apache Kafka.

## Architecture

| Module / service | Purpose |
|---|---|
| `booking-server-command` | Handles write operations, stores application data in MySQL, and publishes Kafka events. |
| `booking-server-query` | Handles read operations and maintains Elasticsearch data from Kafka events. |
| `booking-care-document` | Shared Java library containing event definitions, response models, and constants; packaged into both backend applications. |
| Apache Kafka | Transfers events between Command and Query. |
| Elasticsearch | Provides the Query service's search and read storage. |
| Redis | Provides caching and temporary data storage. |

Command and Query run as separate applications. The shared library does not require a separate container or port.

## Prerequisites

For building the project:

- Git.
- Java 17. Maven wrappers are included in the backend modules.
- Python 3 for deployment script checks.

For deployment:

- An AWS EC2 instance running Amazon Linux 2023, x86_64. The current demo configuration targets 4 GiB RAM and 2–3 concurrent testers.
- [Docker Engine](https://docs.docker.com/engine/install/) and [Docker Compose](https://docs.docker.com/compose/install/), version 2.30 or newer, on EC2.
- MySQL installed directly on EC2; the current setup uses MySQL Community 8.4.
- Amazon ECR repositories, IAM roles, and GitHub Actions environment configuration as described in the [AWS setup guide](deploy/aws/SETUP-AWS.md).

## Installation and deployment

### 1. Clone the repository

```bash
git clone https://github.com/Chaosql/Bekoo_HuongDichVu.git
cd Bekoo_HuongDichVu
```

### 2. Configure the deployment environment

Copy the environment template on your computer:

```bash
cp deploy/aws/env.aws.example .env.aws
chmod 600 .env.aws
```

For an existing checkout with a configured `.env.aws`, keep that file instead of replacing it with the template.

Fill in the required values, then save the file contents as the GitHub Actions secret `BEKOO_ENV` in the `production` environment. Keep actual passwords, tokens, and SSH private keys out of Git.

For an existing schema, use `DB_DDL_AUTO=validate`. Use `update` only for the initial schema bootstrap described in the setup guide. Email, Cloudinary, VNPay, and administrator seeding require their corresponding environment values before those features can be tested.

### 3. Prepare AWS and deploy

Follow [SETUP-AWS.md](deploy/aws/SETUP-AWS.md) to configure EC2, native MySQL, Docker networking, ECR, IAM, and GitHub secrets and variables.

The deployment flow is:

```text
Push to main → GitHub Actions build and verify → Amazon ECR
             → SSH to EC2 → Docker Compose → Health checks / rollback
```

Set the repository variable `AWS_DEPLOY_ENABLED=true` after provisioning is complete. Push to `main`, or manually run the [deployment workflow](https://github.com/Chaosql/Bekoo_HuongDichVu/actions/workflows/deploy-aws.yml). Command and Query deploy using the same commit SHA.

EC2 pulls prebuilt images; it does not build Java source. Kafka, Redis, and Elasticsearch run in Docker alongside the two backends. Deployment files are stored in `~/bekoo/runtime` on EC2.

The Compose file is located at `deploy/aws/compose.yaml` and requires generated runtime environment files, ECR images, and a provisioned Docker network. Running `docker compose up -d` from the repository root is not the setup flow for this repository.

## API documentation

The current demo uses the EC2 public IP with separate backend ports:

| Backend | Base URL | Swagger UI |
|---|---|---|
| Command | `http://54.255.60.109:8083` | [Command Swagger](http://54.255.60.109:8083/swagger-ui/index.html) |
| Query | `http://54.255.60.109:8084` | [Query Swagger](http://54.255.60.109:8084/swagger-ui/index.html) |

Enable `SWAGGER_ENABLED=true` in `BEKOO_ENV` and allow inbound TCP ports 8083 and 8084 in the EC2 Security Group. When deploying to another server, update the IP in the application URLs and firewall rules.

Use Command APIs for write operations and Query APIs for reads. Some legacy read endpoints in Command are marked deprecated and appear crossed out in Swagger. Endpoints that require authentication need a valid bearer token entered through **Authorize**.

The demo URLs use HTTP. A frontend served over HTTPS requires an HTTPS backend endpoint or a suitable HTTPS proxy to avoid browser mixed-content restrictions.

## Build and verification

Run these commands from the repository root:

```bash
# Install the shared library first.
bash booking-server-query/mvnw -B -f booking-care-document/pom.xml clean install

# Build and run the selected backend tests.
bash booking-server-command/mvnw -B -f booking-server-command/pom.xml clean verify '-Dtest=*Test'
bash booking-server-query/mvnw -B -f booking-server-query/pom.xml clean verify '-Dtest=*Test'

# Verify deployment preparation and failure handling.
python3 -m unittest discover -s deploy/aws/tests -v
```

The `*ApplicationTests` context tests require live external services and are outside the selected test pattern above. See [VALIDATION.md](deploy/aws/VALIDATION.md) for verification details and the AWS guide for deployment checks.

## Contributing

Contributions are welcome. Open an [issue](https://github.com/Chaosql/Bekoo_HuongDichVu/issues) to report a bug or discuss a change, then submit a pull request with a clear description and relevant verification results.

## Contact

- GitHub: [Chaosql](https://github.com/Chaosql)
- Project discussions and bug reports: [GitHub Issues](https://github.com/Chaosql/Bekoo_HuongDichVu/issues)

## License

This project is licensed under the [GNU General Public License v3.0](LICENSE).
