// Tests IoTSupport's backend and frontend in a Kubernetes Job, then builds the iotsupport-app and
// iotsupport-ui images and pins them into IotDeploy, which Argo CD syncs to prd.
//
// The images are built from the tree the suite passed on, so `latest` is tagged at build time and
// there is no promote stage.
//
// Controller config:
//   - Job: IoTSupport
//   - SCM: pvginkel/IoTSupport, branch main
//   - Script Path: Jenkinsfile

library identifier: 'JenkinsPipelineUtils', changelog: false

pipeline {
    agent {
        kubernetes {
            inheritFrom 'jenkins-agent kaniko'
            yamlMergeStrategy merge()
            yaml podYaml(templates: ['k8s'])
        }
    }

    options {
        disableConcurrentBuilds(abortPrevious: true)
        skipDefaultCheckout()
        timeout(time: 60, unit: 'MINUTES')
        timestamps()
    }

    triggers {
        githubPush()
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Test') {
            steps {
                script {
                    // The backend under test calls the homelab-dev realm as the Keycloak admin client.
                    withVault([vaultSecrets: [
                        [path: 'kv/jenkins/keycloak-iotsupport-admin', engineVersion: 2, secretValues: [
                            [envVar: 'KEYCLOAK_ADMIN_CLIENT_ID', vaultKey: 'client_id'],
                            [envVar: 'KEYCLOAK_ADMIN_CLIENT_SECRET', vaultKey: 'client_secret'],
                        ]],
                    ]]) {
                        modernApp.test(
                            job: 'iot-support-validation',
                            install: 'poetry install --no-interaction --without dev',
                            run: 'poetry run',
                            suites: ['backend', 'frontend'],
                            services: [
                                [name: 's3storage', image: 'rustfs/rustfs:latest', env: [
                                    RUSTFS_ACCESS_KEY: 's3storage',
                                    RUSTFS_SECRET_KEY: 's3storage',
                                ]],
                                [name: 'opensearch', image: 'opensearchproject/opensearch:2',
                                    resources: [requests: [memory: '640Mi'], limits: [memory: '640Mi']],
                                    env: [
                                        'discovery.type': 'single-node',
                                        'plugins.security.disabled': 'true',
                                        DISABLE_INSTALL_DEMO_CONFIG: 'true',
                                        'bootstrap.memory_lock': 'false',
                                        OPENSEARCH_JAVA_OPTS: '-Xms192m -Xmx192m -XX:MaxDirectMemorySize=32m -Dnode.processors=1',
                                    ]],
                            ],
                            env: [
                                S3_ENDPOINT_URL: 'http://localhost:9000',
                                S3_ACCESS_KEY_ID: 's3storage',
                                S3_SECRET_ACCESS_KEY: 's3storage',
                                S3_BUCKET_NAME: 'iot-support-validation',
                                KEYCLOAK_BASE_URL: 'http://keycloak.keycloak-dev:8080/',
                                KEYCLOAK_REALM: 'homelab-dev',
                                OIDC_TOKEN_URL: 'http://keycloak.keycloak-dev:8080/realms/homelab-dev/protocol/openid-connect/token',
                                ELASTICSEARCH_URL: 'http://localhost:9200',
                            ],
                            secrets: ['KEYCLOAK_ADMIN_CLIENT_ID', 'KEYCLOAK_ADMIN_CLIENT_SECRET'],
                        )
                    }
                }
            }
        }

        stage('Build iotsupport-app image') {
            steps {
                container('kaniko') {
                    script {
                        helmCharts.kaniko2(
                            dockerfile: 'backend/Dockerfile',
                            context: 'backend',
                            destinations: [
                                "registry:5000/iotsupport-app:${currentBuild.number}",
                                'registry:5000/iotsupport-app:latest',
                            ]
                        )
                    }
                }
            }
        }

        stage('Build iotsupport-ui image') {
            steps {
                // The frontend shows the commit it was built from, and its build context holds no
                // .git to read it from.
                sh 'git rev-parse HEAD > frontend/git-rev'
                container('kaniko') {
                    script {
                        helmCharts.kaniko2(
                            dockerfile: 'frontend/Dockerfile',
                            context: 'frontend',
                            destinations: [
                                "registry:5000/iotsupport-ui:${currentBuild.number}",
                                'registry:5000/iotsupport-ui:latest',
                            ]
                        )
                    }
                }
            }
        }

        stage('Write image pins') {
            steps {
                container('k8s') {
                    script {
                        cicd.writeVersionPins(repo: 'pvginkel/IotDeploy', pins: [
                            'config/prd/values.yaml': [
                                'images.iotsupport': ":${currentBuild.number}",
                                'images.iotsupportUI': ":${currentBuild.number}",
                            ],
                        ])
                    }
                }
            }
        }
    }
}
