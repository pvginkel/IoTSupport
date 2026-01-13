# Asset Upload Migration - Improved Approach

## Overview

Instead of updating `upload.sh` scripts across 8+ repositories, centralize the upload logic in the existing `JenkinsPipelineUtils` shared library. This eliminates code duplication and makes future changes a single-file update.

## Step 1: Add `uploadAsset` to Jenkins Shared Library

**Repository:** `pvginkel/JenkinsPipelineUtils.git`
**File:** `vars/helmCharts.groovy`

Add this function (follows the existing pattern of `scp`, `rsync`, `ssh`):

```groovy
def uploadAsset(String file, String host = 'iotsupport.iotsupport.svc.cluster.local') {
    def timestamp = sh(script: 'date -u +"%Y-%m-%dT%H:%M:%SZ"', returnStdout: true).trim()
    def signature = sh(
        script: "echo -n '${timestamp}' | openssl dgst -sha256 -sign \$WORKSPACE/HelmCharts/assets/kubernetes-signing-key | base64 -w 0",
        returnStdout: true
    ).trim()

    sh """
        curl --fail --silent --show-error --output - \
            -F "file=@${file}" \
            -F "timestamp=${timestamp}" \
            -F "signature=${signature}" \
            http://${host}/api/assets
    """
}
```

## Step 2: Update Jenkinsfiles

### pvginkel/CalendarDisplay.git - `Jenkinsfile`

**Before (lines 31-44):**
```groovy
stage('Deploy calendar display') {
    dir('HelmCharts') {
        git branch: 'main',
            credentialsId: '5f6fbd66-b41c-405f-b107-85ba6fd97f10',
            url: 'https://github.com/pvginkel/HelmCharts.git'
    }

    dir('CalendarDisplay') {
        sh 'cp build/esp32-calendar-display.bin calendar-display-ota.bin'

        sh 'chmod +x scripts/upload.sh'
        sh 'scripts/upload.sh ../HelmCharts/assets/kubernetes-signing-key calendar-display-ota.bin'
    }
}
```

**After:**
```groovy
stage('Deploy calendar display') {
    dir('HelmCharts') {
        git branch: 'main',
            credentialsId: '5f6fbd66-b41c-405f-b107-85ba6fd97f10',
            url: 'https://github.com/pvginkel/HelmCharts.git'
    }

    helmCharts.uploadAsset('CalendarDisplay/build/esp32-calendar-display.bin')
}
```

---

### pvginkel/ThermostatDisplay.git - `Jenkinsfile`

**Before (lines 30-45):**
```groovy
stage('Deploy thermostat display') {
    dir('HelmCharts') {
        git branch: 'main',
            credentialsId: '5f6fbd66-b41c-405f-b107-85ba6fd97f10',
            url: 'https://github.com/pvginkel/HelmCharts.git'
    }

    dir('ThermostatDisplay') {
        sh 'cp build/esp32-thermostat-display.bin thermostat-display-ota.bin'

        sh 'scripts/upload.sh ../HelmCharts/assets/kubernetes-signing-key thermostat-display-ota.bin'
    }
}
```

**After:**
```groovy
stage('Deploy thermostat display') {
    dir('HelmCharts') {
        git branch: 'main',
            credentialsId: '5f6fbd66-b41c-405f-b107-85ba6fd97f10',
            url: 'https://github.com/pvginkel/HelmCharts.git'
    }

    helmCharts.uploadAsset('ThermostatDisplay/build/esp32-thermostat-display.bin')
}
```

---

### pvginkel/InfraStatisticsDisplay.git - `Jenkinsfile`

Apply same pattern - replace `upload.sh` call with:
```groovy
helmCharts.uploadAsset('InfraStatisticsDisplay/build/<binary-name>.bin')
```

---

### pvginkel/PaperClock.git - `Jenkinsfile`

Apply same pattern - replace `upload.sh` call with:
```groovy
helmCharts.uploadAsset('PaperClock/build/<binary-name>.bin')
```

---

### pvginkel/Intercom.git - `Jenkinsfile`

Apply same pattern - replace `upload.sh` call with:
```groovy
helmCharts.uploadAsset('Intercom/build/<binary-name>.bin')
```

---

### pvginkel/SomfyRemote.git - `Jenkinsfile`

Apply same pattern - replace `upload.sh` call with:
```groovy
helmCharts.uploadAsset('SomfyRemote/build/<binary-name>.bin')
```

---

### pvginkel/ThermostatProxy.git - `Jenkinsfile`

Apply same pattern - replace `upload.sh` call with:
```groovy
helmCharts.uploadAsset('ThermostatProxy/build/<binary-name>.bin')
```

---

### pvginkel/UnderfloorHeatingController.git - `Jenkinsfile`

Apply same pattern - replace `upload.sh` call with:
```groovy
helmCharts.uploadAsset('UnderfloorHeatingController/build/<binary-name>.bin')
```

## Step 3: Delete upload.sh Scripts

After confirming the new approach works, delete `scripts/upload.sh` from each repository:

- [ ] `pvginkel/CalendarDisplay.git`
- [ ] `pvginkel/InfraStatisticsDisplay.git`
- [ ] `pvginkel/PaperClock.git`
- [ ] `pvginkel/ThermostatDisplay.git`
- [ ] `pvginkel/Intercom.git`
- [ ] `pvginkel/SomfyRemote.git`
- [ ] `pvginkel/ThermostatProxy.git`
- [ ] `pvginkel/UnderfloorHeatingController.git`

## Step 4: Update Test Script

**Repository:** `pvginkel/DockerImages.git`
**File:** `iotsupport/scripts/upload-test.sh`

Update URL from `/assetctl/upload.php` to `/api/assets`:

```bash
curl \
    --output - \
    -F "file=@../src/html/esp32/ota/esp32-thermostat-display.bin" \
    -F "timestamp=$TIMESTAMP" \
    -F "signature=$SIGNATURE" \
    http://127.0.0.1/api/assets
```

## Step 5: Remove Legacy PHP Endpoint

Once all projects are migrated and verified:

- [ ] Delete `/assetctl/upload.php` from iotsupport container
- [ ] Remove any nginx routing for the old endpoint

## Rollout Order

1. **JenkinsPipelineUtils** - Add `uploadAsset` function
2. **One test project** (e.g., ThermostatDisplay) - Update Jenkinsfile, verify build works
3. **Remaining projects** - Update Jenkinsfiles
4. **Cleanup** - Delete `upload.sh` scripts and legacy PHP endpoint

## Verification

After each Jenkinsfile update, trigger a build and verify:
- Build completes successfully
- Asset appears in the assets directory
- Response shows JSON: `{"filename": "...", "size": ..., "uploaded_at": "..."}`
