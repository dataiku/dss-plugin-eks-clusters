pipeline {
    options {
        disableConcurrentBuilds()
        timestamps()
    }

    agent { label 'dss-plugin-tests' }

    stages {
        stage('Lint') {
            steps {
                sh 'make lint'
            }
        }

        stage('Compile Python') {
            steps {
                sh 'make compile-python'
            }
        }

        stage('Validate JSON Descriptors') {
            steps {
                sh 'make validate-json'
            }
        }

        stage('Check Generated Files') {
            steps {
                sh 'make check-generated-files'
            }
        }

        stage('Run Unit Tests') {
            steps {
                sh 'make tests'
            }
        }

        stage('Build Plugin') {
            steps {
                sh 'make plugin'
                archiveArtifacts artifacts: 'dist/*.zip', fingerprint: true
            }
        }
    }

    post {
        always {
            script {
                if (fileExists('tests/allure_report')) {
                    allure([
                        includeProperties: false,
                        jdk: '',
                        properties: [],
                        reportBuildPolicy: 'ALWAYS',
                        results: [[path: 'tests/allure_report']]
                    ])
                }

                def status = currentBuild.currentResult
                def statusFields = [
                    env.BUILD_URL,
                    env.CHANGE_TITLE,
                    env.CHANGE_AUTHOR,
                    env.CHANGE_URL,
                    env.BRANCH_NAME,
                    status
                ].collect { field -> (field ?: '').replaceAll(/[;\r\n]/, ' ') }

                writeFile file: '.build-status-line', text: statusFields.join(';') + ';\n'

                sh '''
                    mkdir -p "$HOME/daily-statuses"
                    file_name=$(echo "$JOB_NAME" | tr '/' '-').status
                    touch "$HOME/daily-statuses/$file_name"
                    cat .build-status-line >> "$HOME/daily-statuses/$file_name"
                '''

                cleanWs()
            }
        }
    }
}
