import org.jenkinsci.plugins.pipeline.modeldefinition.Utils

library identifier: 'JenkinsPipelineUtils', changelog: false

podTemplate(inheritFrom: 'jenkins-agent kaniko', containers: [
    containerTemplates.k8s('k8s')
]) {
    node(POD_LABEL) {
        def gitRev
        def k8sNamespace = kubectl.currentNamespace()

        stage('Cloning repo') {
            def scmVars = checkout scm
            gitRev = scmVars.GIT_COMMIT
        }

        stage('Run validation') {
            container('k8s') {
                // Resolve the Playwright version from the (workspace-root) lockfile
                // to select the matching base image (browsers pre-baked).
                def playwrightVersion = sh(
                    script: "grep -m1 '^  playwright@' pnpm-lock.yaml | sed 's/.*@//;s/://'",
                    returnStdout: true,
                ).trim()
                def validationImage = "registry:5000/modern-app-dev-playwright:playwright-${playwrightVersion}"
                echo "Validation image: ${validationImage}"

                // Stream the whole monorepo working tree in instead of baking an image.
                sh "tar czf /tmp/context.tar.gz --exclude=.git --exclude=node_modules --exclude=.venv --exclude=test-results --exclude=.pnpm-store ."

                withVault([vaultSecrets: [
                    [path: 'kv/jenkins/keycloak-iotsupport-admin', engineVersion: 2, secretValues: [
                        [envVar: 'KEYCLOAK_ADMIN_CLIENT_ID', vaultKey: 'client_id'],
                        [envVar: 'KEYCLOAK_ADMIN_CLIENT_SECRET', vaultKey: 'client_secret'],
                    ]],
                ]]) {
                    def suites = ['backend', 'frontend']
                    def jobName = "iot-support-validation-${BUILD_NUMBER}"

                    try {
                        kubectl.startJob("""\
                            apiVersion: batch/v1
                            kind: Job
                            metadata:
                                name: ${jobName}
                                namespace: ${k8sNamespace}
                                labels:
                                    app.kubernetes.io/name: iot-support-validation
                                    app.kubernetes.io/managed-by: jenkins
                                    jenkins/build-number: "${BUILD_NUMBER}"
                            spec:
                                backoffLimit: 0
                                activeDeadlineSeconds: 3600
                                ttlSecondsAfterFinished: 3600
                                template:
                                    spec:
                                        restartPolicy: Never
                                        tolerations:
                                            - key: size
                                              operator: Equal
                                              value: large
                                              effect: PreferNoSchedule
                                        containers:
                                            - name: validation
                                              image: ${validationImage}
                                              imagePullPolicy: Always
                                              securityContext:
                                                  runAsUser: 1000
                                                  runAsGroup: 1000
                                              command: ["sh", "-c"]
                                              args:
                                                  - |
                                                    mkdir -p /work/staging /work/results
                                                    echo "Waiting for code upload..."
                                                    while [ ! -f /work/staging/ready ]; do sleep 1; done
                                                    echo "Code received, extracting..."
                                                    tar xzf /work/staging/context.tar.gz -C /work
                                                    rm -rf /work/staging
                                                    cd /work && poetry install --no-interaction --without dev
                                                    poetry run run-suite --output-mode full --junitxml-dir /work/results --retries 2
                                                    echo \$? > /work/results/exit-code
                                                    sleep infinity
                                              resources:
                                                  requests:
                                                      cpu: "1"
                                                      memory: 3584Mi
                                              env:
                                                  - name: S3_ENDPOINT_URL
                                                    value: http://localhost:9000
                                                  - name: S3_ACCESS_KEY_ID
                                                    value: minioadmin
                                                  - name: S3_SECRET_ACCESS_KEY
                                                    value: minioadmin
                                                  - name: S3_BUCKET_NAME
                                                    value: "iot-support-validation"
                                                  - name: KEYCLOAK_BASE_URL
                                                    value: "${KEYCLOAK_TEST_BASE_URL}"
                                                  - name: KEYCLOAK_REALM
                                                    value: "${KEYCLOAK_TEST_REALM}"
                                                  - name: KEYCLOAK_ADMIN_CLIENT_ID
                                                    value: "${KEYCLOAK_ADMIN_CLIENT_ID}"
                                                  - name: KEYCLOAK_ADMIN_CLIENT_SECRET
                                                    value: "${KEYCLOAK_ADMIN_CLIENT_SECRET}"
                                                  - name: OIDC_TOKEN_URL
                                                    value: "${KEYCLOAK_TEST_OIDC_TOKEN_URL}"
                                                  - name: ELASTICSEARCH_URL
                                                    value: http://localhost:9200
                                            - name: minio
                                              image: minio/minio
                                              command: ["minio"]
                                              args: ["server", "/data"]
                                              env:
                                                  - name: MINIO_ROOT_USER
                                                    value: minioadmin
                                                  - name: MINIO_ROOT_PASSWORD
                                                    value: minioadmin
                                            - name: opensearch
                                              image: opensearchproject/opensearch:2
                                              resources:
                                                  requests:
                                                      memory: 640Mi
                                                  limits:
                                                      memory: 640Mi
                                              env:
                                                  - name: discovery.type
                                                    value: single-node
                                                  - name: plugins.security.disabled
                                                    value: "true"
                                                  - name: DISABLE_INSTALL_DEMO_CONFIG
                                                    value: "true"
                                                  - name: bootstrap.memory_lock
                                                    value: "false"
                                                  - name: OPENSEARCH_JAVA_OPTS
                                                    value: "-Xms192m -Xmx192m -XX:MaxDirectMemorySize=32m -Dnode.processors=1"
                        """.stripIndent())

                        def podName = kubectl.getJobPodName(jobName, k8sNamespace)
                        kubectl.waitForContainer(podName, 'validation', k8sNamespace)
                        sh "kubectl cp -n ${k8sNamespace} -c validation /tmp/context.tar.gz ${podName}:/work/staging/context.tar.gz"
                        sh "kubectl exec -n ${k8sNamespace} -c validation ${podName} -- touch /work/staging/ready"

                        // The container stays alive (sleep infinity) after running,
                        // so we wait for the exit-code file and then copy results
                        // out while it's still running.
                        kubectl.waitForFile(podName, 'validation', k8sNamespace, '/work/results/exit-code')

                        kubectl.savePodLogs(podName, 'validation', k8sNamespace, 'validation-raw.log')
                        utils.cleanLog('validation-raw.log', 'validation.log')

                        sh 'mkdir -p test-results'
                        sh "kubectl cp -n ${k8sNamespace} -c validation ${podName}:/work/results/. test-results/"

                        def exitCode = fileExists('test-results/exit-code') ? readFile('test-results/exit-code').trim() : ''

                        // Generate a summary from the SUITE_RESULT markers in the log.
                        // run-suite emits one marker per JUnit XML; the file stem is the
                        // suite name (backend, frontend). Group by suite via prefix match.
                        def log = readFile('validation.log')
                        def resultLines = log.split('\n').findAll { it.startsWith('===SUITE_RESULT:') }
                        def summaryLines = []
                        def totalP = 0, totalF = 0, totalS = 0

                        suites.each { suite ->
                            def suiteLines = resultLines.findAll { line ->
                                def name = line.replace('===SUITE_RESULT:', '').split(':')[0]
                                name == suite || name.startsWith("${suite}-")
                            }
                            if (suiteLines) {
                                def p = 0, f = 0, s = 0
                                suiteLines.each { line ->
                                    def parts = line.replace('===SUITE_RESULT:', '').replace('===', '').split(':')
                                    p += parts[1] as int; f += parts[2] as int; s += parts[3] as int
                                }
                                totalP += p; totalF += f; totalS += s
                                summaryLines << String.format('  %-12s %3d passed  %3d failed  %3d skipped', suite, p, f, s)
                            } else {
                                summaryLines << String.format('  %-12s status unknown (no test results produced)', suite)
                            }
                        }

                        def summary = [
                            '',
                            '============================================',
                            '  TEST SUMMARY',
                            '============================================',
                            *summaryLines,
                            '--------------------------------------------',
                            String.format('  %-12s %3d passed  %3d failed  %3d skipped', 'TOTAL', totalP, totalF, totalS),
                            '============================================',
                        ].join('\n')
                        writeFile file: 'validation-summary.log', text: summary + '\n'

                        // Clean up intermediate files.
                        sh 'rm -f validation-raw.log /tmp/context.tar.gz test-results/exit-code'

                        archiveArtifacts artifacts: 'validation*.log, test-results/*.xml', allowEmptyArchive: true
                        junit testResults: 'test-results/*.xml', allowEmptyResults: true

                        currentBuild.description = "exit=${exitCode ?: 'n/a'}, ${totalP} passed, ${totalF} failed, ${totalS} skipped"

                        if (!exitCode) {
                            def failReason = kubectl.getJobFailReason(jobName, k8sNamespace)
                            def msg = "Validation failed: no exit code recorded"
                            if (failReason) {
                                msg += " (job: ${failReason})"
                            }
                            error(msg)
                        } else if (exitCode != '0') {
                            error("Validation failed: exit code ${exitCode}")
                        }
                    } finally {
                        kubectl.deleteJob(jobName, k8sNamespace)
                    }
                }
            }
        }

        stage('Building iot-support') {
            container('kaniko') {
                helmCharts.kaniko("backend/Dockerfile", "backend", [
                    "registry:5000/iotsupport-app:${currentBuild.number}",
                    "registry:5000/iotsupport-app:latest"
                ])
            }
        }

        stage('Building iot-support-frontend') {
            writeFile file: 'frontend/git-rev', text: gitRev

            container('kaniko') {
                helmCharts.kaniko("frontend/Dockerfile", ".", [
                    "registry:5000/iotsupport-ui:${currentBuild.number}",
                    "registry:5000/iotsupport-ui:latest"
                ])
            }
        }

        stage('Deploy Helm charts') {
            cicd.helmDeploy()
        }
    }
}
