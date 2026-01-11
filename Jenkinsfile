import org.jenkinsci.plugins.pipeline.modeldefinition.Utils

library('JenkinsPipelineUtils') _

podTemplate(inheritFrom: 'jenkins-agent kaniko') {
    node(POD_LABEL) {
        stage('Cloning repo') {
            git branch: 'main',
                credentialsId: '5f6fbd66-b41c-405f-b107-85ba6fd97f10',
                url: 'https://github.com/pvginkel/IoTSupport.git'
        }

        stage("Building IoTSupport") {
            container('kaniko') {
                helmCharts.kaniko([
                    "registry:5000/iotsupport-app:${currentBuild.number}",
                    "registry:5000/iotsupport-app:latest"
                ])
            }
        }

        stage('Deploy Helm charts') {
            build job: 'HelmCharts', wait: false
        }
    }
}
