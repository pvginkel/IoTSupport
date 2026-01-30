import org.jenkinsci.plugins.pipeline.modeldefinition.Utils

library('JenkinsPipelineUtils') _

podTemplate(inheritFrom: 'jenkins-agent kaniko') {
    node(POD_LABEL) {
        stage('Cloning repo') {
            git branch: 'main',
                credentialsId: '5f6fbd66-b41c-405f-b107-85ba6fd97f10',
                url: 'https://github.com/pvginkel/IoTSupportUI.git'
        }

        stage("Building IoTSupport UI") {
            // Docker can't access the .git folder so we provide the rev of HEAD here.
            sh 'git rev-parse HEAD > git-rev'

            container('kaniko') {
                helmCharts.kaniko([
                    "registry:5000/iotsupport-ui:${currentBuild.number}",
                    "registry:5000/iotsupport-ui:latest"
                ])
            }
        }

        stage('Deploy Helm charts') {
            build job: 'HelmCharts', wait: false
        }
    }
}
